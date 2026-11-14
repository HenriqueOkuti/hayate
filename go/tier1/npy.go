package tier1

import (
	"encoding/binary"
	"fmt"
	"math"
	"os"
	"regexp"
	"strconv"
	"strings"
)

var (
	npyDescr = regexp.MustCompile(`'descr':\s*'([^']+)'`)
	npyOrder = regexp.MustCompile(`'fortran_order':\s*(True|False)`)
	npyShape = regexp.MustCompile(`'shape':\s*\(([^)]*)\)`)
)

// readNpy reads a little-endian, C-order .npy file and returns its dtype, shape and raw data.
func readNpy(path string) (string, []int, []byte, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return "", nil, nil, err
	}
	if len(b) < 10 || string(b[1:6]) != "NUMPY" {
		return "", nil, nil, fmt.Errorf("%s: not a .npy file", path)
	}
	var hlen, off int
	if b[6] == 1 {
		hlen, off = int(binary.LittleEndian.Uint16(b[8:10])), 10
	} else {
		hlen, off = int(binary.LittleEndian.Uint32(b[8:12])), 12
	}
	header := string(b[off : off+hlen])
	d := npyDescr.FindStringSubmatch(header)
	o := npyOrder.FindStringSubmatch(header)
	s := npyShape.FindStringSubmatch(header)
	if d == nil || o == nil || s == nil || o[1] != "False" {
		return "", nil, nil, fmt.Errorf("%s: unsupported header %q", path, header)
	}
	var shape []int
	for p := range strings.SplitSeq(s[1], ",") {
		if p = strings.TrimSpace(p); p != "" {
			v, err := strconv.Atoi(p)
			if err != nil {
				return "", nil, nil, err
			}
			shape = append(shape, v)
		}
	}
	return d[1], shape, b[off+hlen:], nil
}

// ReadFloat32 reads a float32 .npy array (any shape) as a flat slice, with its shape.
func ReadFloat32(path string) ([]float32, []int, error) {
	dtype, shape, raw, err := readNpy(path)
	if err != nil {
		return nil, nil, err
	}
	if dtype != "<f4" {
		return nil, nil, fmt.Errorf("%s: dtype %s, want <f4", path, dtype)
	}
	out := make([]float32, len(raw)/4)
	for i := range out {
		out[i] = math.Float32frombits(binary.LittleEndian.Uint32(raw[4*i:]))
	}
	return out, shape, nil
}

// ReadFloat64 reads a float64 .npy array as a flat slice, with its shape.
func ReadFloat64(path string) ([]float64, []int, error) {
	dtype, shape, raw, err := readNpy(path)
	if err != nil {
		return nil, nil, err
	}
	if dtype != "<f8" {
		return nil, nil, fmt.Errorf("%s: dtype %s, want <f8", path, dtype)
	}
	out := make([]float64, len(raw)/8)
	for i := range out {
		out[i] = math.Float64frombits(binary.LittleEndian.Uint64(raw[8*i:]))
	}
	return out, shape, nil
}

func writeNpy(path, descr string, shape []int, data []byte) error {
	dims := make([]string, len(shape))
	for i, d := range shape {
		dims[i] = strconv.Itoa(d)
	}
	sh := strings.Join(dims, ", ")
	if len(shape) == 1 {
		sh += ","
	}
	header := fmt.Sprintf("{'descr': '%s', 'fortran_order': False, 'shape': (%s), }", descr, sh)
	// pad so the data starts on a multiple of 64 bytes, header ending in a newline (format 1.0)
	pad := 64 - (10+len(header)+1)%64
	header += strings.Repeat(" ", pad%64) + "\n"
	out := make([]byte, 0, 10+len(header)+len(data))
	out = append(out, "\x93NUMPY\x01\x00"...)
	out = binary.LittleEndian.AppendUint16(out, uint16(len(header)))
	out = append(out, header...)
	out = append(out, data...)
	return os.WriteFile(path, out, 0o644)
}

// WriteFloat32 writes a little-endian, C-order float32 .npy file.
func WriteFloat32(path string, v []float32, shape ...int) error {
	b := make([]byte, 4*len(v))
	for i, x := range v {
		binary.LittleEndian.PutUint32(b[4*i:], math.Float32bits(x))
	}
	return writeNpy(path, "<f4", shape, b)
}

// WriteFloat64 writes a little-endian, C-order float64 .npy file.
func WriteFloat64(path string, v []float64, shape ...int) error {
	b := make([]byte, 8*len(v))
	for i, x := range v {
		binary.LittleEndian.PutUint64(b[8*i:], math.Float64bits(x))
	}
	return writeNpy(path, "<f8", shape, b)
}

// ReadInt8 reads an int8 .npy file.
func ReadInt8(path string) ([]int8, []int, error) {
	descr, shape, data, err := readNpy(path)
	if err != nil {
		return nil, nil, err
	}
	if descr != "|i1" && descr != "<i1" {
		return nil, nil, fmt.Errorf("%s: dtype %s, want int8", path, descr)
	}
	out := make([]int8, len(data))
	for i, b := range data {
		out[i] = int8(b)
	}
	return out, shape, nil
}
