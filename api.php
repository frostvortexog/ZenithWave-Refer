<?php
include "../config.php";
include "../functions.php";

$id=$_GET['id'];

$device=$_SERVER['REMOTE_ADDR'].$_SERVER['HTTP_USER_AGENT'];

$user=db_get("users","id=eq.$id")[0];

if($user["device_id"] && $user["device_id"]!=$device){
exit("Already used");
}

db_update("users","id=eq.$id",[
"verified"=>true,
"device_id"=>$device
]);
