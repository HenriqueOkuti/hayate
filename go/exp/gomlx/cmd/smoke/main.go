// Command smoke checks that a GoMLX backend runs here: it prints the backend, then times a
// 4096 x 4096 float32 matrix product (about 137 GFLOP for 1 product).
package main

import (
	"fmt"
	"time"

	"github.com/gomlx/compute"
	"github.com/gomlx/compute/dtypes"
	"github.com/gomlx/compute/shapes"
	_ "github.com/gomlx/gomlx/backends/default"
	. "github.com/gomlx/gomlx/core/graph"
)

func main() {
	backend := compute.MustNew()
	fmt.Printf("backend: %s\n", backend.Description())
	const n = 4096
	exec := MustNewExec(backend, func(g *Graph) *Node {
		a := Iota(g, shapes.Make(dtypes.Float32, n, n), 1)
		a = MulScalar(a, 1.0/n)
		return ReduceAllSum(MatMul(a, a))
	})
	for i := range 4 {
		t0 := time.Now()
		out := exec.MustExec1()
		v := out.Value()
		dt := time.Since(t0)
		fmt.Printf("run %d: sum %v in %v (%.0f GFLOP/s)\n", i, v, dt, 2*float64(n*n*n)/dt.Seconds()/1e9)
	}
}
