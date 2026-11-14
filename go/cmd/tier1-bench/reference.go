package main

// The reference check (decision 0008). A busy desktop slows every configuration by about the
// same amount while the trials still agree, so the trial spread cannot catch it. Each run
// therefore times one fixed configuration before and after the grid and compares the slower of
// the two readings with the last quiet reading of the same harness, profile and model bundle,
// kept in results/bench-reference.json (shared with scripts/bench_tier1.py). A run more than
// refThreshold slower is marked busy and does not replace the stored reading.

import (
	"encoding/json"
	"errors"
	"io/fs"
	"math"
	"os"
)

const (
	refMaxChars  = 3000
	refBatch     = 1
	refCalls     = 2000
	refThreshold = 0.10
	refFile      = "bench-reference.json"
)

type reading struct {
	P50 float64 `json:"p50_us_per_page"`
	P99 float64 `json:"p99_us_per_page"`
}

type baseline struct {
	reading
	Created string `json:"created"`
	Commit  string `json:"commit"`
	Source  string `json:"source"`
}

type refCheck struct {
	Config          map[string]int `json:"config"`
	Before          reading        `json:"before"`
	After           reading        `json:"after"`
	Baseline        *baseline      `json:"baseline"`
	Slowdown        *float64       `json:"slowdown"`
	Threshold       float64        `json:"threshold"`
	Status          string         `json:"status"`
	BaselineUpdated bool           `json:"baseline_updated"`
}

func baselineKey(harness, profile, bundleSHA string) string {
	return harness + "/" + profile + "/" + bundleSHA[:16]
}

// worse is the slower of two readings, quantile by quantile.
func worse(a, b reading) reading {
	return reading{max(a.P50, b.P50), max(a.P99, b.P99)}
}

// judge compares the slower reading with the stored one: "busy" above the threshold, "quiet"
// otherwise, "no-baseline" when nothing is stored yet.
func judge(before, after reading, base *baseline, threshold float64) (*float64, string) {
	if base == nil || base.P50 <= 0 {
		return nil, "no-baseline"
	}
	s := math.Round((worse(before, after).P50/base.P50-1)*1e4) / 1e4
	if s > threshold {
		return &s, "busy"
	}
	return &s, "quiet"
}

func loadBaselines(path string) (map[string]baseline, error) {
	m := map[string]baseline{}
	b, err := os.ReadFile(path)
	if errors.Is(err, fs.ErrNotExist) {
		return m, nil
	}
	if err != nil {
		return nil, err
	}
	return m, json.Unmarshal(b, &m)
}

func saveBaselines(path string, m map[string]baseline) error {
	b, err := json.MarshalIndent(m, "", " ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(b, '\n'), 0o644)
}

// referenceCheck judges a run and, when it is quiet, has no baseline yet or accept is set,
// stores its reading as the new baseline under key.
func referenceCheck(path, key string, before, after reading, accept bool, created, commit, source string) (refCheck, error) {
	m, err := loadBaselines(path)
	if err != nil {
		return refCheck{}, err
	}
	var base *baseline
	if b, ok := m[key]; ok {
		base = &b
	}
	slow, status := judge(before, after, base, refThreshold)
	c := refCheck{
		Config:    map[string]int{"max_chars": refMaxChars, "batch": refBatch, "calls": refCalls},
		Before:    before,
		After:     after,
		Baseline:  base,
		Slowdown:  slow,
		Threshold: refThreshold,
		Status:    status,
	}
	if status != "busy" || accept {
		m[key] = baseline{worse(before, after), created, commit, source}
		if err := saveBaselines(path, m); err != nil {
			return c, err
		}
		c.BaselineUpdated = true
	}
	return c, nil
}
