import React from 'react';
import { SubscriptionCard } from './SubscriptionCard';
import { ReferralCard } from './ReferralCard';

interface HomePageProps {
  subscription: {
    isActive: boolean;
    daysLeft?: number;
    totalDays?: number;
    hasTrial: boolean;
    hasUsedTrial: boolean;
  };
  referralData: {
    referralCode: string;
    referralsCount: number;
    earnings: number;
  };
  onActivateTrial: () => void;
  onRenew: () => void;
  onBuy: () => void;
  onCopyReferral: () => void;
  onWithdraw: () => void;
  referralCopied: boolean;
}

export function HomePage({
  subscription,
  referralData,
  onActivateTrial,
  onRenew,
  onBuy,
  onCopyReferral,
  onWithdraw,
  referralCopied,
}: HomePageProps) {
  return (
    <div className="pb-20 space-y-0">
      <SubscriptionCard
        subscription={subscription}
        onActivateTrial={onActivateTrial}
        onRenew={onRenew}
        onBuy={onBuy}
      />
      
      <ReferralCard
        referralCode={referralData.referralCode}
        referralsCount={referralData.referralsCount}
        earnings={referralData.earnings}
        onCopy={onCopyReferral}
        onWithdraw={onWithdraw}
        copied={referralCopied}
      />
    </div>
  );
}
