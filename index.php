<?php
include "config.php";
include "functions.php";

checkLeaveAndDeduct();

$update = json_decode(file_get_contents("php://input"), true);

$message = $update["message"] ?? null;
$callback = $update["callback_query"] ?? null;

if ($message) {

    $text = $message["text"];
    $user_id = $message["from"]["id"];
    $chat_id = $message["chat"]["id"];

    // START + REFERRAL
    if (strpos($text, "/start") === 0) {

        $ref = explode(" ", $text)[1] ?? null;

        $user = db_get("users", "id=eq.$user_id");

        if (!$user) {

            db_insert("users", [
                "id" => $user_id,
                "referrer" => $ref
            ]);

            // ADD POINT
            if ($ref && $ref != $user_id) {

                $refUser = db_get("users", "id=eq.$ref");

                if ($refUser) {
                    db_update("users", "id=eq.$ref", [
                        "points" => $refUser[0]["points"] + 1
                    ]);

                    bot("sendMessage", [
                        "chat_id" => $ref,
                        "text" => "🎉 New referral! +1 point"
                    ]);
                }
            }
        }

        // FORCE JOIN
  bot("sendMessage", [
    "chat_id" => $chat_id,
    "text" => "🔒 Join all channels first",
    "reply_markup" => json_encode([
        "inline_keyboard" => [
            [["text"=>"📢 Channel 1","url"=>"https://t.me/ZenithWave_Shein"]],
            [["text"=>"📢 Channel 2","url"=>"https://t.me/ZenithWaveLoots"]],
            [["text"=>"📢 Channel 3","url"=>"https://t.me/ZenithWave_Shein_Backup"]],
            [["text"=>"✅ Joined All Channels","callback_data"=>"joined"]]
        ]
    ])
]);

        // VERIFY
        bot("sendMessage", [
            "chat_id" => $chat_id,
            "text" => "🔐 Complete verification",
            "reply_markup" => json_encode([
                "inline_keyboard" => [
                    [["text" => "Verify Now", "url" => "https://zenithwave-refer-1.onrender.com/web/verify.php?id=$user_id"]],
                    [["text" => "Check Verification", "callback_data" => "check"]]
                ]
            ])
        ]);
    }

    // JOIN BUTTON
    if ($text == "✅ Joined All Channels") {

        if (!isJoined($user_id)) {
            bot("sendMessage", [
                "chat_id" => $chat_id,
                "text" => "❌ Join all channels first"
            ]);
            exit;
        }
        
        bot("sendMessage", [
            "chat_id" => $chat_id,
            "text" => "🔐 Verify",
            "reply_markup" => json_encode([
                "inline_keyboard" => [
                    [["text" => "Verify Now", "url" => "https://zenithwave-refer-1.onrender.com/web/verify.php?id=$user_id"]],
                    [["text" => "Check Verification", "callback_data" => "check"]]
                ]
            ])
        ]);
    }

    // USER MENU
    if ($text == "📊 Stats") {
        $u = db_get("users", "id=eq.$user_id")[0];
        bot("sendMessage", [
            "chat_id" => $chat_id,
            "text" => "Points: ".$u["points"]
        ]);
    }

    if ($text == "🔗 Referral") {
        bot("sendMessage", [
            "chat_id" => $chat_id,
            "text" => "https://t.me/ZenithWave_Refer_Bot?start=$user_id"
        ]);
    }

    // WITHDRAW
    if ($text == "💰 Withdraw") {

        $u = db_get("users", "id=eq.$user_id")[0];

        if ($u["points"] < $withdraw_points) {
            bot("sendMessage", ["chat_id"=>$chat_id,"text"=>"❌ Not enough points"]);
            exit;
        }

        $coupon = db_get("coupons", "limit=1");

        if (!$coupon) {
            bot("sendMessage", ["chat_id"=>$chat_id,"text"=>"❌ Out of stock"]);
            exit;
        }

        $code = $coupon[0]["code"];

        db_update("users", "id=eq.$user_id", [
            "points"=>$u["points"] - $withdraw_points
        ]);

        db_insert("redeems", [
            "user_id"=>$user_id,
            "coupon"=>$code
        ]);

        bot("sendMessage", ["chat_id"=>$chat_id,"text"=>"🎁 $code"]);

        foreach ($admin_ids as $admin) {
            bot("sendMessage", [
                "chat_id"=>$admin,
                "text"=>"💰 Redeemed\nUser: $user_id\nCode: $code\n".date("Y-m-d H:i:s")
            ]);
        }
    }

    // ADMIN PANEL
    if (in_array($user_id, $admin_ids) && $text == "/admin") {

        bot("sendMessage", [
            "chat_id"=>$chat_id,
            "text"=>"Admin Panel",
            "reply_markup"=>json_encode([
                "keyboard"=>[
                    [["text"=>"➕ Add Coupon"],["text"=>"➖ Remove Coupon"]],
                    [["text"=>"📦 Stock"],["text"=>"📜 Logs"]],
                    [["text"=>"⚙ Change Withdraw"]]
                ],
                "resize_keyboard"=>true
            ])
        ]);
    }

    // ADD COUPON
    if ($text == "➕ Add Coupon") {
        file_put_contents("state.txt", "add");
        bot("sendMessage", ["chat_id"=>$chat_id,"text"=>"Send coupons line by line"]);
    } elseif (file_get_contents("state.txt") == "add") {

        $codes = explode("\n", $text);

        foreach ($codes as $c) {
            db_insert("coupons", ["code"=>$c]);
        }

        unlink("state.txt");

        bot("sendMessage", ["chat_id"=>$chat_id,"text"=>"✅ Added"]);
    }

    // STOCK
    if ($text == "📦 Stock") {
        $c = db_get("coupons");
        bot("sendMessage", ["chat_id"=>$chat_id,"text"=>"Stock: ".count($c)]);
    }

    // LOGS
    if ($text == "📜 Logs") {
        $logs = db_get("redeems","order=time.desc&limit=10");

        $msg="Logs:\n\n";
        foreach($logs as $l){
            $msg.="User: ".$l["user_id"]."\nCode: ".$l["coupon"]."\n".$l["time"]."\n\n";
        }

        bot("sendMessage",["chat_id"=>$chat_id,"text"=>$msg]);
    }
}
