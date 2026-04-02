// Test script for Account Linking Frontend Implementation
// Run this in browser console to verify functionality

console.log('🔍 Account Linking Frontend Test Started');

// Test 1: Check if SettingsPage component exists and has correct props
console.log('✅ Test 1: SettingsPage component check');
try {
  const settingsPage = document.querySelector('[data-testid="settings-page"]') ||
                      document.querySelector('.settings-page') ||
                      document.querySelector('h1')?.textContent?.includes('Настройки') ? document.body : null;

  if (settingsPage) {
    console.log('✅ SettingsPage component found');
  } else {
    console.log('⚠️ SettingsPage component not found (may be rendered conditionally)');
  }
} catch (e) {
  console.log('❌ Error checking SettingsPage:', e);
}

// Test 2: Check if account linking buttons exist
console.log('✅ Test 2: Account linking buttons check');
setTimeout(() => {
  const linkButtons = document.querySelectorAll('button');
  let telegramButton = false;
  let browserButton = false;

  linkButtons.forEach(button => {
    const text = button.textContent?.toLowerCase() || '';
    if (text.includes('привязать telegram')) telegramButton = true;
    if (text.includes('привязать браузер')) browserButton = true;
  });

  console.log('Telegram link button:', telegramButton ? '✅ Found' : '❌ Not found');
  console.log('Browser link button:', browserButton ? '✅ Found' : '❌ Not found');

  // Test 3: Check account status indicators
  console.log('✅ Test 3: Account status indicators check');
  const checkmarks = document.querySelectorAll('svg');
  let emailStatus = false;
  let telegramStatus = false;

  checkmarks.forEach(svg => {
    if (svg.outerHTML.includes('M9 12l2 2 4-4')) { // Checkmark icon
      const parentText = svg.closest('div')?.textContent || '';
      if (parentText.includes('Email')) emailStatus = true;
      if (parentText.includes('Telegram')) telegramStatus = true;
    }
  });

  console.log('Email status indicator:', emailStatus ? '✅ Found' : '❌ Not found');
  console.log('Telegram status indicator:', telegramStatus ? '✅ Found' : '❌ Not found');

  // Test 4: Check API functions exist
  console.log('✅ Test 4: API functions check');
  if (typeof window !== 'undefined') {
    // This would need to be checked in the React component context
    console.log('⚠️ API functions check requires React dev tools inspection');
    console.log('Check: handleLinkTelegram and handleLinkBrowser functions exist in App component');
  }

  console.log('🎉 Account Linking Frontend Test Completed');
  console.log('');
  console.log('📋 Manual Verification Steps:');
  console.log('1. Open Settings page');
  console.log('2. Look for "Аккаунты" section');
  console.log('3. Check account status (Email/Telegram linked or not)');
  console.log('4. Click "Привязать Telegram" button (if available)');
  console.log('5. Verify new window opens with Telegram link');
  console.log('6. Click "Привязать браузерный аккаунт" button (if available)');
  console.log('7. Verify redirect to Telegram deep link');
  console.log('8. Check toast notifications appear');
}, 1000);

// Helper function to test API calls (run manually)
window.testAccountLinkingAPI = async () => {
  console.log('🧪 Testing Account Linking API calls...');

  const token = localStorage.getItem('remnastore.browser_access_token');
  if (!token) {
    console.log('❌ No access token found');
    return;
  }

  const baseUrl = 'http://localhost:8000'; // Adjust as needed

  try {
    // Test Telegram link generation
    console.log('Testing /api/v1/accounts/link-telegram...');
    const telegramResponse = await fetch(`${baseUrl}/api/v1/accounts/link-telegram`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (telegramResponse.ok) {
      const data = await telegramResponse.json();
      console.log('✅ Telegram link generated:', data.link_url);
    } else {
      console.log('❌ Telegram link failed:', telegramResponse.status);
    }

    // Test Browser link generation
    console.log('Testing /api/v1/accounts/link-browser...');
    const browserResponse = await fetch(`${baseUrl}/api/v1/accounts/link-browser`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (browserResponse.ok) {
      const data = await browserResponse.json();
      console.log('✅ Browser link generated:', data.link_url);
    } else {
      console.log('❌ Browser link failed:', browserResponse.status);
    }

  } catch (e) {
    console.log('❌ API test error:', e);
  }
};

console.log('💡 To test API calls, run: testAccountLinkingAPI()');
console.log('🔍 Test will run automatically in 1 second...');