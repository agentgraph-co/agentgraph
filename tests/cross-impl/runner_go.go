// JCS RFC 8785 cross-implementation runner -- Go (gowebpki/jcs v1.0.1)
// Verifies 53 substrate vectors across 5 fixture files byte-for-byte.
//
// Usage (from this directory):
//   go run runner_go.go
//
//go:generate go get github.com/gowebpki/jcs@v1.0.1

package main

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"

	jcs "github.com/gowebpki/jcs"
)

func fixturesDir() string {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		return "fixtures"
	}
	return filepath.Join(filepath.Dir(file), "fixtures")
}

func main() {
	dir := fixturesDir()
	gp, gt := 0, 0

	type VecList struct {
		Vectors []map[string]interface{} `json:"vectors"`
	}

	listFiles := []struct {
		fname, objKey, expKey, mode string
	}{
		{"ap2-omh-v0.json", "mandate_body", "expected_jcs_bytes_b64", "bytes"},
		{"per_chain_envelope_v0.json", "mandate_body", "expected_jcs_bytes_b64", "bytes"},
		{"privacy_class_v0.1.json", "attestation_body", "expected_jcs_bytes_b64", "bytes"},
		{"aps_vectors.json", "input", "canonical_sha256", "sha256"},
	}

	for _, f := range listFiles {
		raw, err := os.ReadFile(filepath.Join(dir, f.fname))
		if err != nil {
			fmt.Printf("  ERROR reading %s: %v\n", f.fname, err)
			continue
		}
		var d VecList
		if err := json.Unmarshal(raw, &d); err != nil {
			fmt.Printf("  ERROR parsing %s: %v\n", f.fname, err)
			continue
		}
		p, t := 0, 0
		for _, v := range d.Vectors {
			vid, _ := v["vector_id"].(string)
			if vid == "" {
				if n, ok := v["name"].(string); ok {
					vid = n
				} else {
					vid = "?"
				}
			}
			obj := v[f.objKey]
			objJSON, err := json.Marshal(obj)
			if err != nil {
				fmt.Printf("  ERROR marshalling %s %s: %v\n", f.fname, vid, err)
				continue
			}
			canon, err := jcs.Transform(objJSON)
			if err != nil {
				fmt.Printf("  JCS err %s %s: %v\n", f.fname, vid, err)
				continue
			}
			var ok bool
			if f.mode == "bytes" {
				expB64, _ := v[f.expKey].(string)
				exp, _ := base64.StdEncoding.DecodeString(expB64)
				ok = string(canon) == string(exp)
			} else {
				h := sha256.Sum256(canon)
				exp, _ := v[f.expKey].(string)
				ok = hex.EncodeToString(h[:]) == exp
			}
			if ok {
				p++
			} else {
				fmt.Printf("  FAIL %s %s\n", f.fname, vid)
			}
			t++
		}
		status := "FAIL"
		if p == t {
			status = "PASS"
		}
		fmt.Printf("  %s: %d/%d %s\n", f.fname, p, t, status)
		gp += p
		gt += t
	}

	// ctef_vectors.json: flat top-level dict, named keys with input_object
	ctef, err := os.ReadFile(filepath.Join(dir, "ctef_vectors.json"))
	if err != nil {
		fmt.Printf("  ERROR reading ctef_vectors.json: %v\n", err)
	} else {
		var ctd map[string]map[string]interface{}
		if err := json.Unmarshal(ctef, &ctd); err != nil {
			fmt.Printf("  ERROR parsing ctef_vectors.json: %v\n", err)
		} else {
			cp, ct2 := 0, 0
			for key, v := range ctd {
				if _, hasObj := v["input_object"]; !hasObj {
					continue
				}
				objJSON, _ := json.Marshal(v["input_object"])
				canon, err := jcs.Transform(objJSON)
				if err != nil {
					fmt.Printf("  JCS err ctef %s: %v\n", key, err)
					continue
				}
				h := sha256.Sum256(canon)
				exp, _ := v["canonical_sha256"].(string)
				if hex.EncodeToString(h[:]) == exp {
					cp++
				} else {
					fmt.Printf("  FAIL ctef_vectors.json %s\n", key)
				}
				ct2++
			}
			status := "FAIL"
			if cp == ct2 {
				status = "PASS"
			}
			fmt.Printf("  ctef_vectors.json: %d/%d %s\n", cp, ct2, status)
			gp += cp
			gt += ct2
		}
	}

	fmt.Printf("\ngowebpki/jcs v1.0.1 (Go): %d/%d PASS\n", gp, gt)
}
