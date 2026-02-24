<?php

function bot($method, $data = []) {
    global $api;
    $url = $api . $method;

    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POSTFIELDS => $data
    ]);

    $res = curl_exec($ch);
    curl_close($ch);

    return json_decode($res, true);
}

function db_get($table, $query = "") {
    global $supabase_url, $supabase_key;

    $url = "$supabase_url/rest/v1/$table?$query";

    $headers = [
        "apikey: $supabase_key",
        "Authorization: Bearer $supabase_key"
    ];

    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);

    $res = curl_exec($ch);
    curl_close($ch);

    return json_decode($res, true);
}

function db_insert($table, $data) {
    global $supabase_url, $supabase_key;

    $ch = curl_init("$supabase_url/rest/v1/$table");

    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "apikey: $supabase_key",
        "Authorization: Bearer $supabase_key",
        "Content-Type: application/json"
    ]);

    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);

    $res = curl_exec($ch);
    curl_close($ch);

    return json_decode($res, true);
}

function db_update($table, $query, $data) {
    global $supabase_url, $supabase_key;

    $ch = curl_init("$supabase_url/rest/v1/$table?$query");

    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "PATCH");

    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "apikey: $supabase_key",
        "Authorization: Bearer $supabase_key",
        "Content-Type: application/json"
    ]);

    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);

    $res = curl_exec($ch);
    curl_close($ch);

    return json_decode($res, true);
}

function isJoined($user_id) {
    global $channels;

    foreach ($channels as $ch) {
        $res = bot("getChatMember", [
            "chat_id" => $ch,
            "user_id" => $user_id
        ]);

        if ($res["result"]["status"] == "left") return false;
    }
    return true;
}

// LEAVE DETECTION
function checkLeaveAndDeduct() {

    $users = db_get("users");

    foreach ($users as $u) {

        $joined = isJoined($u["id"]);

        if (!$joined && $u["referrer"]) {

            $ref = $u["referrer"];

            $refUser = db_get("users", "id=eq.$ref");

            if ($refUser && $refUser[0]["points"] > 0) {

                db_update("users", "id=eq.$ref", [
                    "points" => $refUser[0]["points"] - 1
                ]);

                bot("sendMessage", [
                    "chat_id" => $ref,
                    "text" => "⚠️ Referral left channels. -1 point"
                ]);
            }
        }
    }
}
