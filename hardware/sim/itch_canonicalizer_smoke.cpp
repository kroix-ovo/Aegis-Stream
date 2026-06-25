#include "Vitch_canonicalizer.h"
#include "verilated.h"

#include <array>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace {

void tick(Vitch_canonicalizer& top) {
    top.clk = 0;
    top.eval();
    top.clk = 1;
    top.eval();
    top.clk = 0;
    top.eval();
}

void clear_input(Vitch_canonicalizer& top) {
    for (int i = 0; i < 16; ++i) {
        top.s_payload_tdata[i] = 0;
    }
    top.s_payload_tkeep = 0;
    top.s_payload_tvalid = 0;
    top.s_payload_tlast = 0;
    top.s_payload_timestamp_ns = 0;
}

void set_byte(Vitch_canonicalizer& top, int byte_idx, uint8_t value) {
    const int low_bit = 504 - byte_idx * 8;
    const int word = low_bit / 32;
    const int shift = low_bit % 32;
    const uint32_t mask = 0xffu << shift;
    top.s_payload_tdata[word] = (top.s_payload_tdata[word] & ~mask) |
                                (static_cast<uint32_t>(value) << shift);
}

uint64_t keep_mask(size_t bytes) {
    if (bytes >= 64) {
        return ~uint64_t{0};
    }
    return (uint64_t{1} << bytes) - 1;
}

void drive_message(Vitch_canonicalizer& top, const std::vector<uint8_t>& bytes) {
    clear_input(top);
    for (size_t i = 0; i < bytes.size(); ++i) {
        set_byte(top, static_cast<int>(i), bytes[i]);
    }
    top.s_payload_tkeep = keep_mask(bytes.size());
    top.s_payload_tlast = 1;
    top.s_payload_tvalid = 1;
}

void put16(std::vector<uint8_t>& bytes, size_t off, uint16_t value) {
    bytes[off + 0] = static_cast<uint8_t>((value >> 8) & 0xff);
    bytes[off + 1] = static_cast<uint8_t>(value & 0xff);
}

void put32(std::vector<uint8_t>& bytes, size_t off, uint32_t value) {
    bytes[off + 0] = static_cast<uint8_t>((value >> 24) & 0xff);
    bytes[off + 1] = static_cast<uint8_t>((value >> 16) & 0xff);
    bytes[off + 2] = static_cast<uint8_t>((value >> 8) & 0xff);
    bytes[off + 3] = static_cast<uint8_t>(value & 0xff);
}

void put48(std::vector<uint8_t>& bytes, size_t off, uint64_t value) {
    for (int i = 0; i < 6; ++i) {
        bytes[off + i] = static_cast<uint8_t>((value >> (40 - i * 8)) & 0xff);
    }
}

void put64(std::vector<uint8_t>& bytes, size_t off, uint64_t value) {
    for (int i = 0; i < 8; ++i) {
        bytes[off + i] = static_cast<uint8_t>((value >> (56 - i * 8)) & 0xff);
    }
}

std::vector<uint8_t> add_order() {
    std::vector<uint8_t> bytes(36, 0);
    bytes[0] = 'A';
    put16(bytes, 1, 0x1234);
    put16(bytes, 3, 0x0042);
    put48(bytes, 5, 0x010203040506ull);
    put64(bytes, 11, 0x1112131415161718ull);
    bytes[19] = 'B';
    put32(bytes, 20, 0x0000012c);
    const std::string stock = "AEGIS   ";
    for (size_t i = 0; i < 8; ++i) {
        bytes[24 + i] = static_cast<uint8_t>(stock[i]);
    }
    put32(bytes, 32, 0x000f4240);
    return bytes;
}

std::vector<uint8_t> cancel_order() {
    std::vector<uint8_t> bytes(23, 0);
    bytes[0] = 'X';
    put16(bytes, 1, 0x1234);
    put16(bytes, 3, 0x0043);
    put48(bytes, 5, 0x010203040600ull);
    put64(bytes, 11, 0x1112131415161718ull);
    put32(bytes, 19, 0x00000064);
    return bytes;
}

uint64_t get_bits(const VlWide<8>& word, int low, int width) {
    uint64_t value = 0;
    for (int bit = 0; bit < width; ++bit) {
        const int src = low + bit;
        const int arr = src / 32;
        const int shift = src % 32;
        if ((word[arr] >> shift) & 1u) {
            value |= uint64_t{1} << bit;
        }
    }
    return value;
}

void expect_eq(uint64_t actual, uint64_t expected, const char* name) {
    if (actual != expected) {
        std::cerr << name << ": expected 0x" << std::hex << expected
                  << " got 0x" << actual << std::dec << "\n";
        std::exit(1);
    }
}

void expect_event(Vitch_canonicalizer& top,
                  uint64_t event_type,
                  uint64_t shares,
                  uint64_t price,
                  uint64_t side_flags) {
    if (!top.m_event_tvalid) {
        std::cerr << "expected event valid\n";
        std::exit(1);
    }
    expect_eq(get_bits(top.m_event_tdata, 248, 8), event_type, "event_type");
    expect_eq(get_bits(top.m_event_tdata, 232, 16), 0x1234, "stock_locate");
    expect_eq(get_bits(top.m_event_tdata, 168, 64), 0x1112131415161718ull, "order_ref");
    expect_eq(get_bits(top.m_event_tdata, 136, 32), price, "price");
    expect_eq(get_bits(top.m_event_tdata, 104, 32), shares, "shares");
    expect_eq(get_bits(top.m_event_tdata, 96, 8), side_flags, "side_flags");
}

}  // namespace

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vitch_canonicalizer top;

    clear_input(top);
    top.rst_n = 0;
    top.m_event_tready = 1;
    tick(top);
    top.rst_n = 1;

    drive_message(top, add_order());
    tick(top);
    expect_eq(top.m_error, 0, "add_error");
    expect_event(top, 1, 0x12c, 0x000f4240, 1);

    drive_message(top, cancel_order());
    tick(top);
    expect_eq(top.m_error, 0, "cancel_error");
    expect_event(top, 3, 0x64, 0, 0);

    auto truncated = add_order();
    truncated.resize(35);
    drive_message(top, truncated);
    tick(top);
    expect_eq(top.m_error, 2, "truncated_error");

    std::cout << "itch_canonicalizer smoke test passed\n";
    return 0;
}
