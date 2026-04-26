<?php
// update.php — Körs via Cron (var 5:e minut)
// Läser config.json, hämtar SL-avgångar och genererar en statisk display.html

error_reporting(0);
ini_set('display_errors', '0');

$config_file = __DIR__ . '/config.json';
if (!file_exists($config_file)) {
    die("FEL: config.json saknas. Öppna settings.php för att konfigurera.\n");
}
$config = json_decode(file_get_contents($config_file), true);
$stops  = $config['stops'] ?? [];
if (empty($stops)) {
    die("FEL: Inga hållplatser konfigurerade. Öppna settings.php.\n");
}

// --- API-hämtning ---

function fetch_sl(string $url): ?array {
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
    curl_close($ch);
    if ($err || !$resp) return null;
    return json_decode((string) $resp, true);
}

function build_url(array $stop): string {
    $url = "https://transport.integration.sl.se/v1/sites/{$stop['site_id']}/departures?forecast=90";
    if (!empty($stop['direction'])) $url .= "&direction={$stop['direction']}";
    if (!empty($stop['transport'])) $url .= "&transport={$stop['transport']}";
    return $url;
}

function parse_rows(?array $data, int $count, bool $with_type = false): array {
    $rows = [];
    $deps = $data['departures'] ?? [];
    for ($i = 0; $i < $count; $i++) {
        if (!isset($deps[$i])) break;
        $d    = $deps[$i];
        $mode = $d['line']['transport_mode'] ?? '';
        $type = '';
        if ($with_type) {
            $type_map = ['BUS' => 'Buss', 'SHIP' => 'Båt', 'METRO' => 'T-bana', 'TRAM' => 'Spårv.', 'TRAIN' => 'Tåg'];
            $type = $type_map[$mode] ?? $mode;
        }
        $rows[] = [
            'time' => htmlspecialchars(substr($d['expected'] ?? $d['scheduled'] ?? '', 11, 5)),
            'dest' => htmlspecialchars($d['destination'] ?? ''),
            'line' => htmlspecialchars($d['line']['designation'] ?? ''),
            'type' => $type,
        ];
    }
    return $rows;
}

// Inline-stilar — garanterar rendering på Axema C205
function rows_html(array $rows, bool $with_type = false): string {
    if (empty($rows)) {
        $cols = $with_type ? 4 : 3;
        return "<tr><td colspan=\"{$cols}\" style=\"padding:16px;text-align:center;color:#666;font-style:italic;\">Inga avgångar hittades</td></tr>\n";
    }
    $html = '';
    $border = 'border-bottom:1px solid #dde3ea;';
    foreach ($rows as $i => $r) {
        $bg = ($i % 2 !== 0) ? 'background-color:#f0f4f8;' : 'background-color:#ffffff;';
        $html .= "<tr style=\"{$bg}\">";
        $html .= "<td style=\"{$border}padding:10px 14px;font-size:20px;font-weight:bold;color:#005AA0;width:90px;white-space:nowrap;\">{$r['time']}</td>";
        $html .= "<td style=\"{$border}padding:10px 14px;font-size:18px;\">{$r['dest']}</td>";
        $html .= "<td style=\"{$border}padding:10px 14px;font-size:18px;font-weight:bold;width:80px;\">{$r['line']}</td>";
        if ($with_type) {
            $html .= "<td style=\"{$border}padding:10px 14px;font-size:14px;color:#666;width:60px;\">{$r['type']}</td>";
        }
        $html .= "</tr>\n";
    }
    return $html;
}

// --- Hämta data för alla hållplatser ---
$all_data = [];
$cache = [];
foreach ($stops as $stop) {
    $url  = build_url($stop);
    $data = fetch_sl($url);
    $all_data[] = ['stop' => $stop, 'data' => $data];
    $cache[$stop['site_id']] = $data;
}

$updated  = date('H:i');
$cache['_updated'] = $updated;
file_put_contents(__DIR__ . '/cache.json', json_encode($cache));

// --- Bygg HTML ---
$title    = htmlspecialchars($config['title'] ?? 'Avgångar');
$subtitle = implode(' & ', array_map(function($s) { return htmlspecialchars($s['name']); }, $stops));
$reload_ms = 10 * 60 * 1000;

$th = 'style="padding:7px 14px;font-size:12px;font-weight:bold;text-transform:uppercase;letter-spacing:0.8px;color:#005AA0;text-align:left;"';

$sections_html = '';
foreach ($all_data as $idx => $item) {
    $stop  = $item['stop'];
    $data  = $item['data'];
    $wtype = !empty($stop['show_type']);
    $rows  = parse_rows($data, (int) ($stop['rows'] ?? 8), $wtype);
    $rhtml = rows_html($rows, $wtype);
    $name  = htmlspecialchars($stop['name']);
    $mb    = ($idx < count($all_data) - 1) ? 'margin-bottom:16px;' : '';

    $type_th = $wtype ? "<th {$th} width=\"60\">Typ</th>" : '';

    $sections_html .= <<<SECTION
    <div style="background-color:#ffffff;border:1px solid #dde3ea;{$mb}">
      <div style="background-color:#005AA0;color:#ffffff;font-family:Arial,Helvetica,sans-serif;padding:10px 16px;font-size:15px;font-weight:bold;text-transform:uppercase;letter-spacing:0.5px;">
        {$name}
      </div>
      <table>
        <thead>
          <tr style="background-color:#e6eff7;border-bottom:2px solid #005AA0;">
            <th {$th} width="90">Tid</th>
            <th {$th}>Destination</th>
            <th {$th} width="80">Linje</th>
            {$type_th}
          </tr>
        </thead>
        <tbody>
{$rhtml}        </tbody>
      </table>
    </div>
SECTION;
}

$html = <<<HTML
<!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SL Avgångar</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, Helvetica, sans-serif; background: #f5f7fa; color: #1a2433; }
    table { width: 100%; border-collapse: collapse; }
  </style>
</head>
<body>

  <!-- TOPPMENY -->
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#005AA0;">
    <tr>
      <td style="padding:12px 20px;">
        <table cellpadding="0" cellspacing="0">
          <tr>
            <td style="background-color:#ffffff;color:#005AA0;font-family:Arial,Helvetica,sans-serif;font-weight:900;font-size:20px;width:40px;height:40px;text-align:center;vertical-align:middle;">SL</td>
            <td style="padding-left:14px;">
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:bold;color:#ffffff;">{$title}</div>
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#cce0f0;margin-top:2px;">{$subtitle}</div>
            </td>
          </tr>
        </table>
      </td>
      <td style="padding:12px 20px;text-align:right;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#cce0f0;vertical-align:middle;">
        Uppdaterad {$updated}
      </td>
    </tr>
  </table>

  <!-- INNEHÅLL -->
  <div style="padding:16px;">
{$sections_html}
  </div>

  <div style="padding:8px 16px 14px;font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#999;text-align:center;">
    Data hämtad {$updated} &nbsp;&middot;&nbsp; Sidan laddas om automatiskt var 5:e minut
  </div>

  <script>
    var jitter = Math.floor(Math.random() * 60000);
    // Sprid retry 10–20 s så att 5 skärmar inte slår servern samtidigt vid 502.
    function retryDelay() { return 10000 + Math.floor(Math.random() * 10000); }
    function reload() {
      // HEAD-request: bara headers (~200 B) för att kolla att servern är OK,
      // ingen full nedladdning av display.html (~11 kB) innan navigation.
      fetch('display.html', { method: 'HEAD', cache: 'no-cache' })
        .then(function (r) {
          if (r.ok) { window.location.replace('display.html'); }
          else      { setTimeout(reload, retryDelay()); }
        })
        .catch(function () { setTimeout(reload, retryDelay()); });
    }
    setTimeout(reload, {$reload_ms} + jitter);
  </script>

</body>
</html>
HTML;

file_put_contents(__DIR__ . '/display.html', $html);

$status = 'OK';
$details = [];
foreach ($all_data as $item) {
    $name  = $item['stop']['name'];
    $count = count($item['data']['departures'] ?? []);
    if (!$item['data']) { $status = 'VARNING'; $details[] = "{$name}: FEL"; }
    else { $details[] = "{$name}: {$count} avg"; }
}
echo "{$status} | {$updated} | " . implode(' | ', $details) . "\n";
