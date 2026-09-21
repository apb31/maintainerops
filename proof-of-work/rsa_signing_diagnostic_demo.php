<?php
/**
 * Credential-free RSA-SHA256 signing diagnostic harness.
 *
 * Purpose: demonstrate the mechanics needed to isolate request-signing
 * failures from transport/IP allowlist failures without using production keys.
 * This is intentionally generic and does NOT assume BIGO's canonicalization
 * rules; those must come from the official API specification.
 */

declare(strict_types=1);

function fail(string $message): never {
    fwrite(STDERR, "ERROR: {$message}\n");
    exit(1);
}

$key = openssl_pkey_new([
    'private_key_bits' => 2048,
    'private_key_type' => OPENSSL_KEYTYPE_RSA,
]);
if ($key === false) {
    fail('Could not generate ephemeral RSA keypair.');
}

$privatePem = '';
if (!openssl_pkey_export($key, $privatePem)) {
    fail('Could not export private key.');
}

$details = openssl_pkey_get_details($key);
if ($details === false || empty($details['key'])) {
    fail('Could not derive public key.');
}
$publicPem = $details['key'];

// Replace ONLY after reading the official API signing specification.
// Exact bytes, field order, separators, encoding and timestamp format are
// common sources of signature mismatch.
$canonical = "method=POST\npath=/example\ntimestamp=2026-09-21T00:00:00Z\nbody_sha256="
    . hash('sha256', '{"example":"payload"}');

$signatureRaw = '';
if (!openssl_sign($canonical, $signatureRaw, $privatePem, OPENSSL_ALGO_SHA256)) {
    fail('Signing failed.');
}

$signatureB64 = base64_encode($signatureRaw);
$decoded = base64_decode($signatureB64, true);
if ($decoded === false) {
    fail('Base64 decode failed.');
}

$verify = openssl_verify($canonical, $decoded, $publicPem, OPENSSL_ALGO_SHA256);
if ($verify !== 1) {
    fail('Local signature verification failed.');
}

echo "Canonical bytes (hex): " . bin2hex($canonical) . PHP_EOL;
echo "Canonical SHA-256:      " . hash('sha256', $canonical) . PHP_EOL;
echo "Signature (Base64):     " . $signatureB64 . PHP_EOL;
echo "Local verify:           OK" . PHP_EOL;
echo PHP_EOL;
echo "Diagnostic rule: if local signing/verification is reproducible but the API still rejects the request, compare the exact signed bytes and encoding against the official spec before investigating outbound-IP allowlisting separately." . PHP_EOL;
