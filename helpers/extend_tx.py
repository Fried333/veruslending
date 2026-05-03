#!/usr/bin/env python3
"""
Extend a pre-signed Tx-Repay template by adding new inputs and outputs.
Input 0's pre-existing scriptSig is preserved (since it was signed
SIGHASH_SINGLE|ANYONECANPAY, adding more inputs/outputs doesn't invalidate it).
"""
import struct
import sys
import json

def varint(n):
    if n < 0xfd: return bytes([n])
    if n <= 0xffff: return b'\xfd' + struct.pack('<H', n)
    if n <= 0xffffffff: return b'\xfe' + struct.pack('<I', n)
    return b'\xff' + struct.pack('<Q', n)

def read_varint(b, off):
    v = b[off]
    if v < 0xfd: return v, off+1
    if v == 0xfd: return struct.unpack_from('<H', b, off+1)[0], off+3
    if v == 0xfe: return struct.unpack_from('<I', b, off+1)[0], off+5
    return struct.unpack_from('<Q', b, off+1)[0], off+9

def parse_tx(hex_):
    b = bytes.fromhex(hex_)
    off = 0
    # nVersion (4 bytes, lower 31 bits) | fOverwintered (top bit)
    version_raw = struct.unpack_from('<I', b, off)[0]
    off += 4
    fOverwintered = (version_raw >> 31) & 1
    nVersion = version_raw & 0x7fffffff

    nVersionGroupId = 0
    if fOverwintered:
        nVersionGroupId = struct.unpack_from('<I', b, off)[0]
        off += 4

    vin_count, off = read_varint(b, off)
    vins = []
    for _ in range(vin_count):
        prev_txid = b[off:off+32]
        off += 32
        prev_vout = struct.unpack_from('<I', b, off)[0]
        off += 4
        ss_len, off = read_varint(b, off)
        scriptSig = b[off:off+ss_len]
        off += ss_len
        sequence = struct.unpack_from('<I', b, off)[0]
        off += 4
        vins.append({'prev_txid': prev_txid, 'prev_vout': prev_vout,
                     'scriptSig': scriptSig, 'sequence': sequence})

    vout_count, off = read_varint(b, off)
    vouts = []
    for _ in range(vout_count):
        value = struct.unpack_from('<q', b, off)[0]
        off += 8
        spk_len, off = read_varint(b, off)
        scriptPubKey = b[off:off+spk_len]
        off += spk_len
        vouts.append({'value': value, 'scriptPubKey': scriptPubKey})

    nLockTime = struct.unpack_from('<I', b, off)[0]
    off += 4

    nExpiryHeight = 0
    if fOverwintered:
        nExpiryHeight = struct.unpack_from('<I', b, off)[0]
        off += 4

    # remainder is sapling-specific (valueBalance, shieldedSpends, shieldedOutputs, joinSplits, bindingSig)
    remainder = b[off:]
    return {
        'fOverwintered': fOverwintered,
        'nVersion': nVersion,
        'nVersionGroupId': nVersionGroupId,
        'vins': vins,
        'vouts': vouts,
        'nLockTime': nLockTime,
        'nExpiryHeight': nExpiryHeight,
        'remainder': remainder,
    }

def serialize_tx(tx):
    out = b''
    version_raw = (tx['nVersion'] & 0x7fffffff) | ((tx['fOverwintered'] & 1) << 31)
    out += struct.pack('<I', version_raw)
    if tx['fOverwintered']:
        out += struct.pack('<I', tx['nVersionGroupId'])
    out += varint(len(tx['vins']))
    for v in tx['vins']:
        out += v['prev_txid']
        out += struct.pack('<I', v['prev_vout'])
        out += varint(len(v['scriptSig']))
        out += v['scriptSig']
        out += struct.pack('<I', v['sequence'])
    out += varint(len(tx['vouts']))
    for o in tx['vouts']:
        out += struct.pack('<q', o['value'])
        out += varint(len(o['scriptPubKey']))
        out += o['scriptPubKey']
    out += struct.pack('<I', tx['nLockTime'])
    if tx['fOverwintered']:
        out += struct.pack('<I', tx['nExpiryHeight'])
    out += tx['remainder']
    return out.hex()

def add_input(tx, prev_txid_hex, prev_vout, sequence=0xffffffff):
    """Add an input with empty scriptSig (to be filled by signing)."""
    tx['vins'].append({
        'prev_txid': bytes.fromhex(prev_txid_hex)[::-1],  # reverse to LE
        'prev_vout': prev_vout,
        'scriptSig': b'',
        'sequence': sequence,
    })

def add_output(tx, value_sats, scriptPubKey_hex):
    tx['vouts'].append({
        'value': value_sats,
        'scriptPubKey': bytes.fromhex(scriptPubKey_hex),
    })

def addr_to_p2pkh_spk(addr):
    """For an R-address, return P2PKH scriptPubKey."""
    # Use base58 decode then standard encoding
    import hashlib
    BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = 0
    for c in addr:
        n = n * 58 + BASE58_ALPHABET.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    # Verus R-address: 1 byte version (0x3c) + 20 byte hash160 + 4 byte checksum
    # leading zeros
    pad = 0
    for c in addr:
        if c == '1':
            pad += 1
        else:
            break
    raw = b'\x00' * pad + raw
    if len(raw) != 25:
        raise ValueError(f'expected 25 bytes, got {len(raw)} for {addr}')
    version = raw[0]
    hash160 = raw[1:21]
    # P2PKH: OP_DUP OP_HASH160 <push 20 bytes> hash160 OP_EQUALVERIFY OP_CHECKSIG
    return bytes([0x76, 0xa9, 0x14]) + hash160 + bytes([0x88, 0xac])

if __name__ == '__main__':
    # template: pre-signed Tx-Repay (1 input signed SIGHASH_SINGLE|ANYONECANPAY, 1 output)
    template_hex = open('/tmp/txRepay_template_signed.hex').read().strip()
    tx = parse_tx(template_hex)
    print(f'parsed: {len(tx["vins"])} vins, {len(tx["vouts"])} vouts', file=sys.stderr)
    print(f'vin0 scriptSig len: {len(tx["vins"][0]["scriptSig"])}', file=sys.stderr)
    print(f'vout0 value: {tx["vouts"][0]["value"]}', file=sys.stderr)
    print(f'remainder len: {len(tx["remainder"])}', file=sys.stderr)

    # Add Alice's DAI funding inputs:
    #   Input 1: Tx-A vout 1 (5 DAI from origination)
    #   Input 2: 5202dba1... vout 0 (0.5 DAI from sendcurrency funding)
    add_input(tx, '3b23258b3d21a9e2ca45f7c73762f9790bb488a8fbf0a8aeb1bd9dcdeace168b', 1)
    add_input(tx, '5202dba15e213f180c632a09caee0c9d5a5888daa03787b722ca5f506d91dd43', 0)

    # Add Alice's VRSC return output (9.9999 VRSC = 999990000 sats; collateral 10 - fee 0.0001)
    alice_change = 'RBV6Z3w2HAtVMnifn3hbbYsYNayY2PTHud'
    spk = addr_to_p2pkh_spk(alice_change)
    add_output(tx, 999990000, spk.hex())

    print(f'extended: {len(tx["vins"])} vins, {len(tx["vouts"])} vouts', file=sys.stderr)
    print(serialize_tx(tx))
