import org.webpki.jcs.JsonCanonicalizer;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

/**
 * JCS RFC 8785 cross-implementation runner -- Java (cyberphone/json-canonicalization)
 * Verifies 53 substrate vectors across 5 fixture files byte-for-byte.
 *
 * COMPILE (from tests/cross-impl/):
 *   mkdir -p lib/org/webpki/jcs
 *   Copy DoubleCoreSerializer.java, JsonCanonicalizer.java, NumberToJSON.java
 *   from https://github.com/cyberphone/json-canonicalization src/org/webpki/jcs/
 *   into lib/org/webpki/jcs/ then:
 *
 *     javac lib/org/webpki/jcs/*.java -d lib/
 *     javac -cp lib JcsRunner.java
 *
 * RUN (from tests/cross-impl/):
 *   java -cp .:lib JcsRunner
 */
public class JcsRunner {

    static String hex(byte[] b) {
        StringBuilder sb = new StringBuilder(b.length * 2);
        for (byte x : b) sb.append(String.format("%02x", x & 0xff));
        return sb.toString();
    }

    // Extracts the raw JSON value for key from a JSON object string.
    static String extractJsonValue(String json, String key) {
        String search = "\"" + key + "\"";
        int ki = json.indexOf(search);
        if (ki < 0) return null;
        int colon = json.indexOf(":", ki + search.length());
        if (colon < 0) return null;
        int start = colon + 1;
        while (start < json.length() && Character.isWhitespace(json.charAt(start))) start++;
        char first = json.charAt(start);
        if (first == '{' || first == '[') {
            char open = first, close = (first == '{') ? '}' : ']';
            int depth = 1, i = start + 1;
            boolean inStr = false;
            while (i < json.length() && depth > 0) {
                char c = json.charAt(i);
                if (inStr) {
                    if (c == '\\') { i++; } else if (c == '\"') { inStr = false; }
                } else {
                    if (c == '\"') { inStr = true; }
                    else if (c == open) { depth++; }
                    else if (c == close) { depth--; }
                }
                i++;
            }
            return json.substring(start, i);
        } else if (first == '\"') {
            int i = start + 1;
            while (i < json.length()) {
                char c = json.charAt(i);
                if (c == '\\') { i += 2; continue; }
                if (c == '\"') { i++; break; }
                i++;
            }
            return json.substring(start + 1, i - 1);
        }
        return null;
    }

    // Splits "[{...}, {...}]" into individual JSON object strings.
    static List<String> splitJsonArray(String arr) {
        List<String> result = new ArrayList<>();
        int i = 0;
        while (i < arr.length() && arr.charAt(i) != '[') i++;
        i++;
        while (i < arr.length()) {
            while (i < arr.length() && (Character.isWhitespace(arr.charAt(i)) || arr.charAt(i) == ',')) i++;
            if (i >= arr.length() || arr.charAt(i) == ']') break;
            if (arr.charAt(i) == '{') {
                int depth = 1, start = i++;
                boolean s = false;
                while (i < arr.length() && depth > 0) {
                    char c = arr.charAt(i);
                    if (s) { if (c == '\\') { i++; } else if (c == '\"') { s = false; } }
                    else { if (c == '\"') { s = true; } else if (c == '{') { depth++; } else if (c == '}') { depth--; } }
                    i++;
                }
                result.add(arr.substring(start, i));
            } else { i++; }
        }
        return result;
    }

    // Returns [key, objectJson] pairs for top-level keys with object values.
    static List<String[]> topLevelObjects(String json) {
        List<String[]> result = new ArrayList<>();
        int i = 0;
        while (i < json.length() && json.charAt(i) != '{') i++;
        i++;
        while (i < json.length()) {
            while (i < json.length() && Character.isWhitespace(json.charAt(i))) i++;
            if (i >= json.length() || json.charAt(i) == '}') break;
            if (json.charAt(i) != '\"') { i++; continue; }
            int ks = ++i;
            while (i < json.length()) {
                if (json.charAt(i) == '\\') { i += 2; continue; }
                if (json.charAt(i) == '\"') break;
                i++;
            }
            String key = json.substring(ks, i++);
            while (i < json.length() && json.charAt(i) != ':') i++;
            i++;
            while (i < json.length() && Character.isWhitespace(json.charAt(i))) i++;
            if (i < json.length() && json.charAt(i) == '{') {
                int depth = 1, start = i++;
                boolean s = false;
                while (i < json.length() && depth > 0) {
                    char c = json.charAt(i);
                    if (s) { if (c == '\\') { i++; } else if (c == '\"') { s = false; } }
                    else { if (c == '\"') { s = true; } else if (c == '{') { depth++; } else if (c == '}') { depth--; } }
                    i++;
                }
                result.add(new String[]{key, json.substring(start, i)});
            } else {
                while (i < json.length() && json.charAt(i) != ',' && json.charAt(i) != '}') {
                    if (json.charAt(i) == '\"') {
                        i++;
                        while (i < json.length()) {
                            if (json.charAt(i) == '\\') { i += 2; continue; }
                            if (json.charAt(i) == '\"') break;
                            i++;
                        }
                    }
                    i++;
                }
            }
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        Path fixturesDir;
        try {
            fixturesDir = Paths.get(JcsRunner.class.getProtectionDomain()
                    .getCodeSource().getLocation().toURI()).getParent().resolve("fixtures");
        } catch (Exception e) {
            fixturesDir = Paths.get("fixtures");
        }
        if (!Files.isDirectory(fixturesDir)) fixturesDir = Paths.get("fixtures");

        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        int passed = 0, total = 0;

        // mandate_body -> expected_jcs_bytes_b64
        for (String fname : new String[]{"ap2-omh-v0.json", "per_chain_envelope_v0.json"}) {
            String json = new String(Files.readAllBytes(fixturesDir.resolve(fname)), StandardCharsets.UTF_8);
            String vecs = extractJsonValue(json, "vectors");
            if (vecs == null) { System.out.println(fname + ": ERROR no vectors key"); continue; }
            for (String vec : splitJsonArray(vecs)) {
                String vid = extractJsonValue(vec, "vector_id");
                if (vid == null) vid = "?";
                String body = extractJsonValue(vec, "mandate_body");
                String exp  = extractJsonValue(vec, "expected_jcs_bytes_b64");
                if (body == null || exp == null) continue;
                byte[] canon = new JsonCanonicalizer(body.getBytes(StandardCharsets.UTF_8)).getEncodedUTF8();
                boolean ok = Base64.getEncoder().encodeToString(canon).equals(exp);
                if (ok) passed++;
                total++;
                System.out.println(fname + " " + vid + ": " + (ok ? "PASS" : "FAIL"));
            }
        }

        // attestation_body -> expected_jcs_bytes_b64
        {
            String fname = "privacy_class_v0.1.json";
            String json = new String(Files.readAllBytes(fixturesDir.resolve(fname)), StandardCharsets.UTF_8);
            String vecs = extractJsonValue(json, "vectors");
            if (vecs == null) {
                System.out.println(fname + ": ERROR no vectors key");
            } else {
                for (String vec : splitJsonArray(vecs)) {
                    String vid = extractJsonValue(vec, "vector_id");
                    if (vid == null) vid = "?";
                    String body = extractJsonValue(vec, "attestation_body");
                    String exp  = extractJsonValue(vec, "expected_jcs_bytes_b64");
                    if (body == null || exp == null) continue;
                    byte[] canon = new JsonCanonicalizer(body.getBytes(StandardCharsets.UTF_8)).getEncodedUTF8();
                    boolean ok = Base64.getEncoder().encodeToString(canon).equals(exp);
                    if (ok) passed++;
                    total++;
                    System.out.println(fname + " " + vid + ": " + (ok ? "PASS" : "FAIL"));
                }
            }
        }

        // input -> canonical_sha256
        {
            String fname = "aps_vectors.json";
            String json = new String(Files.readAllBytes(fixturesDir.resolve(fname)), StandardCharsets.UTF_8);
            String vecs = extractJsonValue(json, "vectors");
            if (vecs == null) {
                System.out.println(fname + ": ERROR no vectors key");
            } else {
                for (String vec : splitJsonArray(vecs)) {
                    String vid = extractJsonValue(vec, "name");
                    if (vid == null) vid = extractJsonValue(vec, "vector_id");
                    if (vid == null) vid = "?";
                    String inp = extractJsonValue(vec, "input");
                    String exp = extractJsonValue(vec, "canonical_sha256");
                    if (inp == null || exp == null) continue;
                    byte[] canon = new JsonCanonicalizer(inp.getBytes(StandardCharsets.UTF_8)).getEncodedUTF8();
                    sha256.reset();
                    boolean ok = hex(sha256.digest(canon)).equals(exp);
                    if (ok) passed++;
                    total++;
                    System.out.println(fname + " " + vid + ": " + (ok ? "PASS" : "FAIL"));
                }
            }
        }

        // ctef_vectors: flat named entries with input_object -> canonical_sha256
        {
            String fname = "ctef_vectors.json";
            String json = new String(Files.readAllBytes(fixturesDir.resolve(fname)), StandardCharsets.UTF_8);
            for (String[] entry : topLevelObjects(json)) {
                String inp = extractJsonValue(entry[1], "input_object");
                String exp = extractJsonValue(entry[1], "canonical_sha256");
                if (inp == null || exp == null) continue;
                byte[] canon = new JsonCanonicalizer(inp.getBytes(StandardCharsets.UTF_8)).getEncodedUTF8();
                sha256.reset();
                boolean ok = hex(sha256.digest(canon)).equals(exp);
                if (ok) passed++;
                total++;
                System.out.println(fname + " " + entry[0] + ": " + (ok ? "PASS" : "FAIL"));
            }
        }

        System.out.println("\nJava cyberphone/json-canonicalization: " + passed + "/" + total + " PASS");
    }
}
