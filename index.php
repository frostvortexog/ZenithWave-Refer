<?php

// ================= WEB VERIFY ROUTE =================

if($_SERVER['REQUEST_METHOD'] === 'POST' && strpos($_SERVER['REQUEST_URI'], '/verify') !== false){

    $input = json_decode(file_get_contents("php://input"), true);

    $user = $input["user"];
    $device = $input["device"];

    $supa_url = getenv("SUPABASE_URL");
    $supa_key = getenv("SUPABASE_KEY");

    function db($endpoint,$method="GET",$data=null){
        global $supa_url,$supa_key;

        $ch = curl_init("$supa_url/rest/v1/$endpoint");
        curl_setopt($ch,CURLOPT_RETURNTRANSFER,true);

        $headers = [
            "apikey: $supa_key",
            "Authorization: Bearer $supa_key",
            "Content-Type: application/json"
        ];

        curl_setopt($ch,CURLOPT_HTTPHEADER,$headers);

        if($method!="GET"){
            curl_setopt($ch,CURLOPT_CUSTOMREQUEST,$method);
            curl_setopt($ch,CURLOPT_POSTFIELDS,json_encode($data));
        }

        return json_decode(curl_exec($ch),true);
    }

    // 🔒 Check device already used
    $check = db("users?device_id=eq.$device");

    if(count($check) > 0){
        echo json_encode(["status"=>"error","msg"=>"Device already used"]);
        exit;
    }

    // ✅ Verify user
    db("users?telegram_id=eq.$user","PATCH",[
        "verified"=>true,
        "device_id"=>$device
    ]);

    echo json_encode(["status"=>"success"]);
    exit;
}

// ================= CONFIG =================
$bot_token = getenv("BOT_TOKEN");
$api = "https://api.telegram.org/bot$bot_token/";

$supa_url = getenv("SUPABASE_URL");
$supa_key = getenv("SUPABASE_KEY");

$admin_id = 8537079657; // CHANGE

$channels = ["@ZenithWave_Shein","@ZenithWaveLoots","@ZenithWave_Shein_Backup"];
$verify_url = "zenith-wave-refer-bot.vercel.app"; // CHANGE

// ================= FUNCTIONS =================

function bot($method,$data){
    global $api;
    $ch = curl_init($api.$method);
    curl_setopt($ch,CURLOPT_RETURNTRANSFER,true);
    curl_setopt($ch,CURLOPT_POSTFIELDS,$data);
    return json_decode(curl_exec($ch),true);
}

function db($endpoint,$method="GET",$data=null){
    global $supa_url,$supa_key;

    $ch = curl_init("$supa_url/rest/v1/$endpoint");
    curl_setopt($ch,CURLOPT_RETURNTRANSFER,true);

    $headers = [
        "apikey: $supa_key",
        "Authorization: Bearer $supa_key",
        "Content-Type: application/json"
    ];

    curl_setopt($ch,CURLOPT_HTTPHEADER,$headers);

    if($method!="GET"){
        curl_setopt($ch,CURLOPT_CUSTOMREQUEST,$method);
        curl_setopt($ch,CURLOPT_POSTFIELDS,json_encode($data));
    }

    return json_decode(curl_exec($ch),true);
}

function checkJoin($user){
    global $channels;
    foreach($channels as $ch){
        $res = bot("getChatMember",[
            "chat_id"=>$ch,
            "user_id"=>$user
        ]);
        if($res["result"]["status"]=="left") return false;
    }
    return true;
}

// ================= UPDATE =================

$update = json_decode(file_get_contents("php://input"),true);

// ================= JOIN LEAVE DETECTION =================
if(isset($update["chat_member"])){

$user = $update["chat_member"]["from"]["id"];
$status = $update["chat_member"]["new_chat_member"]["status"];

if($status=="left"){

$u = db("users?telegram_id=eq.$user")[0];

if($u && $u["ref_by"]){

$ref = $u["ref_by"];

db("users?telegram_id=eq.$ref","PATCH",[
"points"=>$u["points"]-1
]);

bot("sendMessage",[
"chat_id"=>$ref,
"text"=>"⚠️ Your referral left. 1 point deducted."
]);

}

}

}

// ================= MESSAGE =================

if(isset($update["message"])){

$msg = $update["message"];
$user = $msg["from"]["id"];
$text = $msg["text"] ?? "";

$ref = str_replace("/start ","",$text);

// USER CHECK
$u = db("users?telegram_id=eq.$user");

if(!$u){

db("users","POST",[
"telegram_id"=>$user,
"points"=>0,
"ref_by"=>$ref,
"verified"=>false
]);

}

// ================= START =================

if($text=="/start" || strpos($text,"/start")!==false){

bot("sendMessage",[
"chat_id"=>$user,
"text"=>"🔒 Join all channels",
"reply_markup"=>json_encode([
"inline_keyboard"=>[
[["text"=>"Channel 1","url"=>"https://t.me/ZenithWave_Shein"]],
[["text"=>"Channel 2","url"=>"https://t.me/ZenithWaveLoots"]],
[["text"=>"Channel 3","url"=>"https://t.me/ZenithWave_Shein_Backup"]],
[["text"=>"✅ Joined","callback_data"=>"check_join"]]
]
])
]);

}

// ================= USER MENU =================

if($text=="📊 Stats"){

$u = db("users?telegram_id=eq.$user")[0];

bot("sendMessage",[
"chat_id"=>$user,
"text"=>"👤 Referrals: ".$u["points"]."\n💰 Points: ".$u["points"]
]);

}

if($text=="🔗 Referral Link"){

$link = "https://t.me/YOUR_BOT?start=$user";

bot("sendMessage",[
"chat_id"=>$user,
"text"=>"Your Link:\n$link"
]);

}

if($text=="💸 Withdraw"){

$u = db("users?telegram_id=eq.$user")[0];
$settings = db("settings?key=eq.withdraw_points")[0]["value"];

if($u["points"] < $settings){

bot("sendMessage",[
"chat_id"=>$user,
"text"=>"❌ Not enough points"
]);
return;
}

$coupons = db("coupons?used=eq.false");

if(!$coupons){

bot("sendMessage",[
"chat_id"=>$user,
"text"=>"❌ Coupons out of stock"
]);
return;
}

$code = $coupons[0]["code"];

db("coupons?id=eq.".$coupons[0]["id"],"PATCH",[
"used"=>true,
"used_by"=>$user
]);

db("users?telegram_id=eq.$user","PATCH",[
"points"=>$u["points"]-$settings
]);

bot("sendMessage",[
"chat_id"=>$user,
"text"=>"🎉 Coupon: $code"
]);

bot("sendMessage",[
"chat_id"=>$admin_id,
"text"=>"User $user redeemed $code"
]);

}

}

// ================= CALLBACK =================

if(isset($update["callback_query"])){

$data = $update["callback_query"]["data"];
$user = $update["callback_query"]["from"]["id"];
$id = $update["callback_query"]["id"];

if($data=="check_join"){

if(checkJoin($user)){

bot("sendMessage",[
"chat_id"=>$user,
"text"=>"🌐 Verify now",
"reply_markup"=>json_encode([
"inline_keyboard"=>[
[["text"=>"Verify Now","url"=>"$verify_url?user=$user"]],
[["text"=>"Check Verification","callback_data"=>"verify_check"]]
]
])
]);

}else{
bot("answerCallbackQuery",[
"callback_query_id"=>$id,
"text"=>"Join all channels!"
]);
}

}

if($data=="verify_check"){

$u = db("users?telegram_id=eq.$user")[0];

if($u["verified"]){

// REFERRAL ADD
if($u["ref_by"]){

$ref = $u["ref_by"];

$refUser = db("users?telegram_id=eq.$ref")[0];

db("users?telegram_id=eq.$ref","PATCH",[
"points"=>$refUser["points"]+1
]);

bot("sendMessage",[
"chat_id"=>$ref,
"text"=>"🎉 New referral joined +1 point"
]);

}

$menu = [
["📊 Stats","🔗 Referral Link"],
["💸 Withdraw"]
];

if($user==$admin_id){
$menu[]=["👑 Admin Panel"];
}

bot("sendMessage",[
"chat_id"=>$user,
"text"=>"✅ Verified",
"reply_markup"=>json_encode([
"keyboard"=>$menu,
"resize_keyboard"=>true
])
]);

}else{
bot("answerCallbackQuery",[
"callback_query_id"=>$id,
"text"=>"Not verified"
]);
}

}

// ================= ADMIN =================

if($data=="admin"){

if($user!=$admin_id) return;

$menu = [
["➕ Add Coupon","➖ Remove Coupon"],
["📦 Stock","📜 Logs"],
["⚙ Change Points"]
];

bot("sendMessage",[
"chat_id"=>$user,
"text"=>"Admin Panel",
"reply_markup"=>json_encode([
"keyboard"=>$menu,
"resize_keyboard"=>true
])
]);

}

}

// ================= ADMIN TEXT =================

if(isset($update["message"])){

$text = $update["message"]["text"];
$user = $update["message"]["from"]["id"];

if($user!=$admin_id) return;

// ADD COUPON
if($text=="➕ Add Coupon"){
bot("sendMessage",["chat_id"=>$user,"text"=>"Send coupons line by line"]);
file_put_contents("step_$user","add");
}

elseif(file_get_contents("step_$user")=="add"){

$codes = explode("\n",$text);

foreach($codes as $c){
db("coupons","POST",["code"=>$c]);
}

unlink("step_$user");

bot("sendMessage",["chat_id"=>$user,"text"=>"Added"]);
}

// REMOVE
if($text=="➖ Remove Coupon"){
file_put_contents("step_$user","remove");
bot("sendMessage",["chat_id"=>$user,"text"=>"Send number"]);
}

elseif(file_get_contents("step_$user")=="remove"){

$list = db("coupons?used=eq.false");

for($i=0;$i<$text;$i++){
db("coupons?id=eq.".$list[$i]["id"],"DELETE");
}

unlink("step_$user");

bot("sendMessage",["chat_id"=>$user,"text"=>"Removed"]);
}

// STOCK
if($text=="📦 Stock"){
$c = db("coupons?used=eq.false");
bot("sendMessage",["chat_id"=>$user,"text"=>"Stock: ".count($c)]);
}

// LOGS
if($text=="📜 Logs"){
$l = db("coupons?used=eq.true&limit=10");
$msg="Last 10:\n";
foreach($l as $x){
$msg .= $x["used_by"]." -> ".$x["code"]."\n";
}
bot("sendMessage",["chat_id"=>$user,"text"=>$msg]);
}

// CHANGE POINTS
if($text=="⚙ Change Points"){
file_put_contents("step_$user","points");
bot("sendMessage",["chat_id"=>$user,"text"=>"Send new value"]);
}

elseif(file_get_contents("step_$user")=="points"){

db("settings?key=eq.withdraw_points","PATCH",[
"value"=>$text
]);

unlink("step_$user");

bot("sendMessage",["chat_id"=>$user,"text"=>"Updated"]);
}

}

?>
