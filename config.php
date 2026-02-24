<?php

$bot_token = getenv("BOT_TOKEN");
$api = "https://api.telegram.org/bot$bot_token/";

$admin_ids = [8537079657]; // YOUR TELEGRAM ID

$channels = [
    "@ZenithWave_Shein",
    "@ZenithWaveLoots",
    "@ZenithWave_Shein_Backup"
];

$withdraw_points = 3;

$supabase_url = getenv("SUPABASE_URL");
$supabase_key = getenv("SUPABASE_KEY");
