<?php
// 使用服务器私有文件保存Cookie加密密钥；不在镜像、仓库或环境变量中保存数据库密码。
$secret = trim(file_get_contents('/run/secrets/phpmyadmin_blowfish'));
if (strlen($secret) !== 32) {
    throw new RuntimeException('phpMyAdmin Cookie密钥必须为32字节');
}
$cfg['blowfish_secret'] = $secret;
$cfg['Servers'][1]['auth_type'] = 'cookie';
$cfg['Servers'][1]['AllowNoPassword'] = false;
$cfg['LoginCookieValidity'] = 1800;
$cfg['LoginCookieRecall'] = false;
$cfg['AllowArbitraryServer'] = false;
$cfg['ShowPhpInfo'] = false;
$cfg['SendErrorReports'] = 'never';
