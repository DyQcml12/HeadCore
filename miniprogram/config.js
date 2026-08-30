// 本地开发基址：微信开发者工具需勾选「不校验合法域名」后可用。
// 真机预览/正式发布：必须替换为已 ICP 备案的 HTTPS 域名（小程序强制 HTTPS + 域名校验，
// 127.0.0.1 只在开发者工具本机调试场景下可访问）。
const apiBaseUrl = "http://127.0.0.1:8000";

// 天气快捷按钮默认查询的城市（后端世界工具走高德天气）。
const weatherCity = "广州";

module.exports = { apiBaseUrl, weatherCity };
