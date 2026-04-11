<?php
// settings.php — Lösenordsskyddad inställningssida för SL Avgångstavla
// Sparar konfiguration till config.json

session_start();
header('Cache-Control: no-store, no-cache, must-revalidate');
header('Connection: close');

$config_file = __DIR__ . '/config.json';
$config = json_decode(file_get_contents($config_file), true);

// --- Första körning: om password_hash är placeholder, sätt till 'admin' ---
if (strpos($config['password_hash'], 'defaulthashplaceholder') !== false) {
    $config['password_hash'] = password_hash('admin', PASSWORD_BCRYPT);
    file_put_contents($config_file, json_encode($config, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
}

$logged_in = !empty($_SESSION['sl_auth']);
$error = '';
$success = '';

// --- Inloggning ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['action'])) {

    if ($_POST['action'] === 'login') {
        if (password_verify($_POST['password'] ?? '', $config['password_hash'])) {
            $_SESSION['sl_auth'] = true;
            $logged_in = true;
        } else {
            $error = 'Fel lösenord.';
        }
    }

    if ($_POST['action'] === 'logout') {
        session_destroy();
        header('Location: settings.php');
        exit;
    }

    // --- Spara inställningar (kräver inloggning) ---
    if ($_POST['action'] === 'save' && $logged_in) {
        $new_config = [
            'password_hash' => $config['password_hash'],
            'title' => trim($_POST['title'] ?? 'Avgångar'),
            'stops' => [],
        ];

        for ($i = 0; $i < 3; $i++) {
            if (empty($_POST["stop_name_{$i}"])) continue;
            $new_config['stops'][] = [
                'name'      => trim($_POST["stop_name_{$i}"]),
                'site_id'   => trim($_POST["stop_id_{$i}"]),
                'direction'  => trim($_POST["stop_dir_{$i}"]),
                'transport'  => trim($_POST["stop_transport_{$i}"] ?? ''),
                'rows'       => (int) ($_POST["stop_rows_{$i}"] ?? 8),
                'show_type'  => !empty($_POST["stop_showtype_{$i}"]),
            ];
        }

        if (empty($new_config['stops'])) {
            $error = 'Minst en hållplats måste anges.';
        } else {
            $config = $new_config;
            file_put_contents($config_file, json_encode($config, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
            $success = 'Inställningar sparade! Ändringar syns vid nästa cron-körning (inom 5 minuter).';
        }
    }

    // --- Byt lösenord ---
    if ($_POST['action'] === 'change_password' && $logged_in) {
        $current = $_POST['current_password'] ?? '';
        $new_pw  = $_POST['new_password'] ?? '';
        $confirm = $_POST['confirm_password'] ?? '';

        if (!password_verify($current, $config['password_hash'])) {
            $error = 'Nuvarande lösenord är felaktigt.';
        } elseif (strlen($new_pw) < 4) {
            $error = 'Nytt lösenord måste vara minst 4 tecken.';
        } elseif ($new_pw !== $confirm) {
            $error = 'Lösenorden matchar inte.';
        } else {
            $config['password_hash'] = password_hash($new_pw, PASSWORD_BCRYPT);
            file_put_contents($config_file, json_encode($config, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
            $success = 'Lösenord ändrat!';
        }
    }
}

// Fyll på till 3 platser för formuläret
$stops = $config['stops'] ?? [];
while (count($stops) < 3) {
    $stops[] = ['name' => '', 'site_id' => '', 'direction' => '2', 'transport' => '', 'rows' => 8, 'show_type' => false];
}

function e($s) { return htmlspecialchars($s ?? '', ENT_QUOTES, 'UTF-8'); }
?><!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Inställningar — SL Avgångstavla</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, Helvetica, sans-serif; background: #f5f7fa; color: #1a2433; }
    .header { background: #005AA0; padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; }
    .header-left { display: flex; align-items: center; gap: 14px; }
    .logo { background: #fff; color: #005AA0; font-weight: 900; font-size: 20px; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; }
    .header h1 { font-size: 20px; color: #fff; font-weight: bold; }
    .header .sub { font-size: 12px; color: #cce0f0; margin-top: 2px; }
    .container { max-width: 700px; margin: 20px auto; padding: 0 16px; }
    .card { background: #fff; border: 1px solid #dde3ea; margin-bottom: 16px; }
    .card-header { background: #005AA0; color: #fff; padding: 10px 16px; font-size: 15px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; }
    .card-body { padding: 16px; }
    label { display: block; font-size: 13px; font-weight: bold; color: #005AA0; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
    input[type="text"], input[type="password"], input[type="number"], select {
      width: 100%; padding: 8px 12px; border: 1px solid #dde3ea; font-size: 14px;
      font-family: Arial, Helvetica, sans-serif; background: #fff; color: #1a2433; margin-bottom: 12px;
    }
    input:focus, select:focus { outline: none; border-color: #005AA0; }
    .checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
    .checkbox-row label { display: inline; margin-bottom: 0; }
    .row { display: flex; gap: 12px; }
    .row > * { flex: 1; }
    .btn { background: #005AA0; color: #fff; border: none; padding: 10px 24px; font-size: 14px; font-weight: bold; cursor: pointer; text-transform: uppercase; letter-spacing: 0.5px; }
    .btn:hover { background: #004080; }
    .btn-secondary { background: #6B7C93; }
    .btn-secondary:hover { background: #556475; }
    .btn-logout { background: transparent; color: #cce0f0; border: 1px solid #cce0f0; padding: 6px 16px; font-size: 12px; font-weight: bold; cursor: pointer; text-transform: uppercase; }
    .btn-logout:hover { background: rgba(255,255,255,0.1); }
    .alert { padding: 10px 14px; margin-bottom: 16px; font-size: 14px; }
    .alert-error { background: #fdecea; color: #b71c1c; border: 1px solid #f5c6cb; }
    .alert-success { background: #e8f5e9; color: #2e7d32; border: 1px solid #c8e6c9; }
    .stop-section { border: 1px solid #e6eff7; padding: 14px; margin-bottom: 14px; background: #fafbfc; }
    .stop-title { font-size: 14px; font-weight: bold; color: #1a2433; margin-bottom: 10px; }
    .help { font-size: 11px; color: #6B7C93; margin-top: -8px; margin-bottom: 12px; }
    .footer { text-align: center; font-size: 11px; color: #999; padding: 8px 16px 20px; }
    hr { border: none; border-top: 1px solid #e6eff7; margin: 16px 0; }
  </style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="logo">SL</div>
    <div>
      <h1>Inställningar</h1>
      <div class="sub">SL Avgångstavla</div>
    </div>
  </div>
  <?php if ($logged_in): ?>
    <form method="post" style="margin:0;">
      <input type="hidden" name="action" value="logout">
      <button type="submit" class="btn-logout">Logga ut</button>
    </form>
  <?php endif; ?>
</div>

<div class="container">

<?php if ($error): ?>
  <div class="alert alert-error"><?= e($error) ?></div>
<?php endif; ?>
<?php if ($success): ?>
  <div class="alert alert-success"><?= e($success) ?></div>
<?php endif; ?>

<?php if (!$logged_in): ?>
  <!-- INLOGGNINGSFORMULÄR -->
  <div class="card">
    <div class="card-header">Logga in</div>
    <div class="card-body">
      <form method="post">
        <input type="hidden" name="action" value="login">
        <label for="password">Lösenord</label>
        <input type="password" id="password" name="password" autofocus>
        <button type="submit" class="btn">Logga in</button>
      </form>
      <p class="help" style="margin-top:12px;">Standardlösenord vid nyinstallation: <strong>admin</strong></p>
    </div>
  </div>

<?php else: ?>
  <!-- HÅLLPLATSER -->
  <form method="post">
    <input type="hidden" name="action" value="save">

    <div class="card">
      <div class="card-header">Visningsinställningar</div>
      <div class="card-body">
        <label for="title">Rubrik på tavlan</label>
        <input type="text" id="title" name="title" value="<?= e($config['title'] ?? 'Avgångar') ?>">
      </div>
    </div>

    <?php for ($i = 0; $i < 3; $i++): $s = $stops[$i]; ?>
    <div class="card">
      <div class="card-header">Hållplats <?= $i + 1 ?><?= $i >= 2 ? ' (valfri)' : '' ?></div>
      <div class="card-body">

        <div class="row">
          <div>
            <label for="stop_name_<?= $i ?>">Namn</label>
            <input type="text" id="stop_name_<?= $i ?>" name="stop_name_<?= $i ?>" value="<?= e($s['name']) ?>" placeholder="T.ex. Nacka Trafikplats">
          </div>
          <div>
            <label for="stop_id_<?= $i ?>">Site-ID</label>
            <input type="text" id="stop_id_<?= $i ?>" name="stop_id_<?= $i ?>" value="<?= e($s['site_id']) ?>" placeholder="T.ex. 4062">
          </div>
        </div>
        <p class="help">Site-ID hittar du via <a href="https://transport.integration.sl.se/v1/sites" target="_blank" style="color:#005AA0;">SL Transport API</a> eller <a href="https://www.trafiklab.se/api/trafiklab-apis/sl/transport/" target="_blank" style="color:#005AA0;">Trafiklab</a>.</p>

        <div class="row">
          <div>
            <label for="stop_dir_<?= $i ?>">Riktning</label>
            <select id="stop_dir_<?= $i ?>" name="stop_dir_<?= $i ?>">
              <option value="1" <?= ($s['direction'] ?? '') === '1' ? 'selected' : '' ?>>1 — Från centrum</option>
              <option value="2" <?= ($s['direction'] ?? '') === '2' ? 'selected' : '' ?>>2 — Mot centrum</option>
              <option value="" <?= ($s['direction'] ?? '') === '' ? 'selected' : '' ?>>Båda riktningar</option>
            </select>
          </div>
          <div>
            <label for="stop_transport_<?= $i ?>">Trafikslag</label>
            <select id="stop_transport_<?= $i ?>" name="stop_transport_<?= $i ?>">
              <option value="" <?= ($s['transport'] ?? '') === '' ? 'selected' : '' ?>>Alla (buss, båt, etc.)</option>
              <option value="BUS" <?= ($s['transport'] ?? '') === 'BUS' ? 'selected' : '' ?>>Bara buss</option>
              <option value="SHIP" <?= ($s['transport'] ?? '') === 'SHIP' ? 'selected' : '' ?>>Bara båt</option>
              <option value="METRO" <?= ($s['transport'] ?? '') === 'METRO' ? 'selected' : '' ?>>Bara tunnelbana</option>
              <option value="TRAM" <?= ($s['transport'] ?? '') === 'TRAM' ? 'selected' : '' ?>>Bara spårvagn</option>
              <option value="TRAIN" <?= ($s['transport'] ?? '') === 'TRAIN' ? 'selected' : '' ?>>Bara pendeltåg</option>
            </select>
          </div>
        </div>

        <div class="row">
          <div>
            <label for="stop_rows_<?= $i ?>">Antal avgångar</label>
            <input type="number" id="stop_rows_<?= $i ?>" name="stop_rows_<?= $i ?>" value="<?= (int) ($s['rows'] ?? 8) ?>" min="1" max="20">
          </div>
          <div style="display:flex;align-items:flex-end;padding-bottom:12px;">
            <div class="checkbox-row">
              <input type="checkbox" id="stop_showtype_<?= $i ?>" name="stop_showtype_<?= $i ?>" value="1" <?= !empty($s['show_type']) ? 'checked' : '' ?>>
              <label for="stop_showtype_<?= $i ?>" style="text-transform:none;font-weight:normal;font-size:14px;">Visa typ-kolumn (Buss/Båt)</label>
            </div>
          </div>
        </div>

      </div>
    </div>
    <?php endfor; ?>

    <button type="submit" class="btn" style="width:100%;margin-bottom:16px;">Spara inställningar</button>
  </form>

  <!-- BYT LÖSENORD -->
  <div class="card">
    <div class="card-header">Byt lösenord</div>
    <div class="card-body">
      <form method="post">
        <input type="hidden" name="action" value="change_password">
        <label for="current_password">Nuvarande lösenord</label>
        <input type="password" id="current_password" name="current_password">
        <label for="new_password">Nytt lösenord</label>
        <input type="password" id="new_password" name="new_password">
        <label for="confirm_password">Bekräfta nytt lösenord</label>
        <input type="password" id="confirm_password" name="confirm_password">
        <button type="submit" class="btn btn-secondary">Byt lösenord</button>
      </form>
    </div>
  </div>

  <div class="footer">
    <a href="display.html" style="color:#005AA0;">Visa avgångstavlan</a>
  </div>

<?php endif; ?>

</div>

</body>
</html>
