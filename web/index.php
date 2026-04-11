<?php
// index.php — Skickar besökaren till den senast genererade statiska sidan.
// Om display.html inte finns ännu (cron har inte kört) visas en väntsida.

header('Cache-Control: no-store, no-cache, must-revalidate');
header('Connection: close');

if (file_exists(__DIR__ . '/display.html')) {
    header('Location: display.html');
    exit;
}

// Väntsida — visas bara vid allra första körningen
?><!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="30">
  <title>SL Avgångar — startar...</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: Arial, Helvetica, sans-serif;
      background: #E6EFF7;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
    }
    .box {
      background: #fff;
      border: 1px solid #D8E2EC;
      padding: 40px 48px;
      text-align: center;
      max-width: 360px;
    }
    .logo {
      background: #005AA0;
      color: #fff;
      font-weight: 900;
      font-size: 28px;
      width: 56px;
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 20px;
    }
    h1 { font-size: 16px; color: #1A2433; margin-bottom: 10px; }
    p  { font-size: 13px; color: #6B7C93; line-height: 1.6; }
  </style>
</head>
<body>
  <div class="box">
    <div class="logo">SL</div>
    <h1>Avgångstavlan startar</h1>
    <p>Väntar på att cron-jobbet ska köra <code>update.php</code>.<br>
       Sidan laddas om automatiskt om 30&nbsp;sekunder.</p>
  </div>
</body>
</html>
