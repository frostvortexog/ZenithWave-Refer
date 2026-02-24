<?php $id=$_GET['id']; ?>
<!DOCTYPE html>
<html>
<head>
<style>
body{display:flex;justify-content:center;align-items:center;height:100vh;background:#0f172a;color:white;font-family:sans-serif;}
.card{background:rgba(255,255,255,0.1);padding:40px;border-radius:20px;backdrop-filter:blur(10px);}
button{padding:15px;background:#22c55e;border:none;border-radius:10px;}
</style>
</head>
<body>
<div class="card">
<h2>Verify Account</h2>
<button onclick="verify()">Verify</button>
</div>
<script>
function verify(){
fetch("api.php?id=<?php echo $id;?>")
.then(()=>window.location="https://t.me/ZenithWave_Refer_Bot");
}
</script>
</body>
</html>
