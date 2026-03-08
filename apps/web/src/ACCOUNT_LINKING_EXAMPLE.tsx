// Example WebApp integration for account linking
// Place this in your React component

import { useState } from 'react';

export function AccountLinkingButtons() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // For browser users to link Telegram
  const handleLinkTelegram = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch('/api/v1/accounts/link-telegram', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        },
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to generate link');
      }

      const data = await response.json();
      
      // Open Telegram bot with linking token
      window.open(data.link_url, '_blank');
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  // For Telegram users to link browser OAuth
  const handleLinkBrowser = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch('/api/v1/accounts/link-browser', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        },
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to generate link');
      }

      const data = await response.json();
      
      // Open browser linking URL (opens bot with deep link)
      window.location.href = data.link_url;
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="account-linking">
      <h2>Link Accounts</h2>
      
      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      <button 
        onClick={handleLinkTelegram}
        disabled={loading}
        className="btn btn-telegram"
      >
        {loading ? 'Processing...' : '🤖 Link Telegram Account'}
      </button>

      <button 
        onClick={handleLinkBrowser}
        disabled={loading}
        className="btn btn-browser"
      >
        {loading ? 'Processing...' : '🌐 Link Browser Account'}
      </button>
    </div>
  );
}
