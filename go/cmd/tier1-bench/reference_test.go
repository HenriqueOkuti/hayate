package main

import (
	"path/filepath"
	"testing"
)

func TestJudge(t *testing.T) {
	base := &baseline{reading: reading{P50: 100, P99: 200}}
	cases := []struct {
		before, after float64
		base          *baseline
		status        string
		slowdown      float64
	}{
		{105, 104, base, "quiet", 0.05},
		{110, 100, base, "quiet", 0.10},
		{100, 125, base, "busy", 0.25},
		{80, 90, base, "quiet", -0.10},
		{100, 100, nil, "no-baseline", 0},
	}
	for _, c := range cases {
		s, status := judge(reading{P50: c.before}, reading{P50: c.after}, c.base, 0.10)
		if status != c.status {
			t.Errorf("judge(%v, %v) = %s, want %s", c.before, c.after, status, c.status)
		}
		if c.base != nil && *s != c.slowdown {
			t.Errorf("judge(%v, %v) slowdown = %v, want %v", c.before, c.after, *s, c.slowdown)
		}
	}
}

func TestReferenceCheckKeepsQuietBaseline(t *testing.T) {
	path := filepath.Join(t.TempDir(), refFile)
	key := baselineKey("go", "local", "0123456789abcdef0123")
	q := reading{P50: 600, P99: 1500}
	c, err := referenceCheck(path, key, q, q, false, "t0", "c0", "first")
	if err != nil || c.Status != "no-baseline" || !c.BaselineUpdated {
		t.Fatalf("first run: %+v, %v", c, err)
	}
	busy := reading{P50: 720, P99: 2000}
	c, err = referenceCheck(path, key, q, busy, false, "t1", "c1", "busy")
	if err != nil || c.Status != "busy" || c.BaselineUpdated {
		t.Fatalf("busy run: %+v, %v", c, err)
	}
	m, _ := loadBaselines(path)
	if m[key].P50 != 600 || m[key].Source != "first" {
		t.Fatalf("busy run replaced the baseline: %+v", m[key])
	}
	c, err = referenceCheck(path, key, busy, busy, true, "t2", "c2", "accepted")
	if err != nil || c.Status != "busy" || !c.BaselineUpdated {
		t.Fatalf("accepted run: %+v, %v", c, err)
	}
	if m, _ = loadBaselines(path); m[key].P50 != 720 {
		t.Fatalf("accept did not store the reading: %+v", m[key])
	}
}
