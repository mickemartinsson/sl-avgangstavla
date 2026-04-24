<?php
// update.php — Körs via Cron hos Loopia (var 5:e minut)
// Hämtar SL-avgångar och genererar en statisk display.html

$NT_URL = "https://transport.integration.sl.se/v1/sites/4062/departures?transport=BUS&direction=2&forecast=90";
$NS_URL = "https://transport.integration.sl.se/v1/sites/4031/departures?direction=2&forecast=90";

function fetch_sl(string $url): ?array {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_CONNECTTIMEOUT => 5,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_HTTPHEADER     => ['Accept: application/json', 'User-Agent: SL-Avgångar/1.0'],
    ]);
    $resp = curl_exec($ch);
    $err  = curl_error($ch);
    curl_close($ch);
    if ($err || !$resp) return null;
    return json_decode((string) $resp, true);
}

function parse_rows(?array $data, int $count, bool $with_type = false): array {
    $rows = [];
    $deps = $data['departures'] ?? [];
    for ($i = 0; $i < $count; $i++) {
        if (!isset($deps[$i])) break;
        $d    = $deps[$i];
        $mode = $d['line']['transport_mode'] ?? '';
        $rows[] = [
            'time' => htmlspecialchars(substr($d['expected'] ?? $d['scheduled'] ?? '', 11, 5)),
            'dest' => htmlspecialchars($d['destination'] ?? ''),
            'line' => htmlspecialchars($d['line']['designation'] ?? ''),
            'type' => $with_type ? ($mode === 'SHIP' ? 'Bat' : 'Buss') : '',
        ];
    }
    return $rows;
}

// Inline-stilar på alla element — garanterar rendering på Axema C205
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

// --- Hämta & spara ---
$nt_data = fetch_sl($NT_URL);
$ns_data = fetch_sl($NS_URL);
$updated = date('H:i');

file_put_contents(__DIR__ . '/cache.json', json_encode([
    'nt' => $nt_data, 'ns' => $ns_data, 'updated' => $updated,
]));

$nt_rows = parse_rows($nt_data, 8);
$ns_rows = parse_rows($ns_data, 8, true);
$nt_html = rows_html($nt_rows);
$ns_html = rows_html($ns_rows, true);

$reload_ms = 5 * 60 * 1000;

// Kolumnrubriks-stil (återanvänds)
$th = 'style="padding:7px 14px;font-size:12px;font-weight:bold;text-transform:uppercase;letter-spacing:0.8px;color:#005AA0;text-align:left;"';

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
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:bold;color:#ffffff;">Avgångar mot centrum</div>
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#cce0f0;margin-top:2px;">Nacka Trafikplats &amp; Nacka Strand</div>
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

    <!-- NACKA TRAFIKPLATS -->
    <div style="background-color:#ffffff;border:1px solid #dde3ea;margin-bottom:16px;">
      <div style="background-color:#005AA0;color:#ffffff;font-family:Arial,Helvetica,sans-serif;padding:10px 16px;font-size:15px;font-weight:bold;text-transform:uppercase;letter-spacing:0.5px;">
        Nacka Trafikplats
      </div>
      <table>
        <thead>
          <tr style="background-color:#e6eff7;border-bottom:2px solid #005AA0;">
            <th {$th} width="90">Tid</th>
            <th {$th}>Destination</th>
            <th {$th} width="80">Linje</th>
          </tr>
        </thead>
        <tbody>
{$nt_html}        </tbody>
      </table>
    </div>

    <!-- NACKA STRAND -->
    <div style="background-color:#ffffff;border:1px solid #dde3ea;">
      <div style="background-color:#005AA0;color:#ffffff;font-family:Arial,Helvetica,sans-serif;padding:10px 16px;font-size:15px;font-weight:bold;text-transform:uppercase;letter-spacing:0.5px;">
        Nacka Strand
      </div>
      <table>
        <thead>
          <tr style="background-color:#e6eff7;border-bottom:2px solid #005AA0;">
            <th {$th} width="90">Tid</th>
            <th {$th}>Destination</th>
            <th {$th} width="80">Linje</th>
            <th {$th} width="60">Typ</th>
          </tr>
        </thead>
        <tbody>
{$ns_html}        </tbody>
      </table>
    </div>

  </div>

  <div style="padding:8px 16px 14px;font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#999;text-align:center;">
    Data hämtad {$updated} &nbsp;&middot;&nbsp; Sidan laddas om automatiskt var 5:e minut
  </div>

  <script>
    var jitter = Math.floor(Math.random() * 60000); // 0–60 s slumpmässig förskjutning
    function reload() {
      fetch('display.html', { cache: 'no-cache' })
        .then(function (r) {
          if (r.ok) { window.location.replace('display.html'); }
          else      { setTimeout(reload, 10000 + Math.floor(Math.random()*20000)); } // 502 → retry 10-30 s (jitter)
        })
        .catch(function () { setTimeout(reload, 10000 + Math.floor(Math.random()*20000)); });
    }
    setTimeout(reload, {$reload_ms} + jitter);
  </script>

</body>
</html>
HTML;

file_put_contents(__DIR__ . '/display.html', $html);

$status = ($nt_data && $ns_data) ? 'OK' : 'VARNING: ett eller flera API-anrop misslyckades';
echo "{$status} | {$updated} | NT: " . count($nt_rows) . " avg | NS: " . count($ns_rows) . " avg\n";
