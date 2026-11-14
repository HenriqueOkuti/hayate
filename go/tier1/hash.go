package tier1

import (
	"encoding/binary"
	"math/bits"
)

// Murmur3 is MurmurHash3 x86 32-bit, as scikit-learn's murmurhash3_32(..., positive=False).
func Murmur3(data []byte, seed uint32) int32 {
	const c1, c2 = 0xcc9e2d51, 0x1b873593
	h := seed
	n := len(data)
	for i := 0; i+4 <= n; i += 4 {
		k := binary.LittleEndian.Uint32(data[i:])
		k *= c1
		k = bits.RotateLeft32(k, 15)
		k *= c2
		h ^= k
		h = bits.RotateLeft32(h, 13)
		h = h*5 + 0xe6546b64
	}
	tail := data[n&^3:]
	var k1 uint32
	switch len(tail) {
	case 3:
		k1 ^= uint32(tail[2]) << 16
		fallthrough
	case 2:
		k1 ^= uint32(tail[1]) << 8
		fallthrough
	case 1:
		k1 ^= uint32(tail[0])
		k1 *= c1
		k1 = bits.RotateLeft32(k1, 15)
		k1 *= c2
		h ^= k1
	}
	h ^= uint32(n)
	h ^= h >> 16
	h *= 0x85ebca6b
	h ^= h >> 13
	h *= 0xc2b2ae35
	h ^= h >> 16
	return int32(h)
}

// bucket is scikit-learn's feature index for a signed hash: abs(h) % n, with -2^31 mapped the
// way _hashing_fast defines it.
func bucket(h int32, n int) int {
	if h == -2147483648 {
		return (2147483647 - (n - 1)) % n
	}
	if h < 0 {
		return int(-h) % n
	}
	return int(h) % n
}
