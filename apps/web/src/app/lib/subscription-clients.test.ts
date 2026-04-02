import { describe, expect, it } from 'vitest';

import {
  SUBSCRIPTION_CLIENTS,
  buildClientImportUrl,
  type SubscriptionClientApp,
} from './subscription-clients';

function findClient(id: string): SubscriptionClientApp {
  const client = Object.values(SUBSCRIPTION_CLIENTS)
    .flat()
    .find((candidate) => candidate.id === id);

  if (!client) {
    throw new Error(`Unknown subscription client: ${id}`);
  }

  return client;
}

describe('buildClientImportUrl', () => {
  it('returns null when the subscription URL is missing', () => {
    expect(buildClientImportUrl(findClient('happ-ios'), null)).toBeNull();
  });

  it('encodes ordinary client links with encodeURIComponent', () => {
    const client = findClient('happ-ios');
    const subscriptionUrl = 'https://example.com/sub?token=abc 123';

    expect(buildClientImportUrl(client, subscriptionUrl)).toBe(
      `happ://add/${encodeURIComponent(subscriptionUrl)}`
    );
  });

  it('base64-encodes client links for clients that require it', () => {
    const client = findClient('shadowrocket-ios');
    const subscriptionUrl = 'https://example.com/sub?token=abc123';

    expect(buildClientImportUrl(client, subscriptionUrl)).toBe(
      `sub://${Buffer.from(subscriptionUrl).toString('base64')}`
    );
  });
});
