<?php
// search.php — Proxy för hållplatssökning via SL Transport API
// Undviker CORS-problem när settings.php söker efter hållplatser

error_reporting(0);
ini_set('display_errors', '0');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: public, max-age=3600');
header('Connection: close');

$q = trim($_GET['q'] ?? '');
if (strlen($q) < 2) {
    echo json_encode([]);
    exit;
}

$url = 'https://transport.integration.sl.se/v1/sites?expand=true';
$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 10,
    CURLOPT_CONNECTTIMEOUT => 5,
    CURLOPT_SSL_VERIFYPEER => true,
    CURLOPT_HTTPHEADER     => ['Accept: application/json', 'User-Agent: SL-Avgangstavla/2.0'],
]);
$resp = curl_exec($ch);
$err  = curl_error($ch);

if ($err || !$resp) {
    http_response_code(502);
    echo json_encode(['error' => 'Kunde inte nå SL API']);
    exit;
}

$sites = json_decode($resp, true);
if (!is_array($sites)) {
    http_response_code(502);
    echo json_encode(['error' => 'Ogiltigt svar från SL API']);
    exit;
}

// Filtrera och returnera matchande hållplatser (max 15)
$q_lower = mb_strtolower($q, 'UTF-8');
$results = [];
foreach ($sites as $site) {
    $name = $site['name'] ?? '';
    if (mb_stripos($name, $q_lower) !== false) {
        $results[] = [
            'id'   => (string) ($site['id'] ?? ''),
            'name' => $name,
        ];
        if (count($results) >= 15) break;
    }
}

echo json_encode($results, JSON_UNESCAPED_UNICODE);
