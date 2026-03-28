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
    referralEarnings: number;
    availableForWithdraw: number;
  };
  onActivateTrial: () => void;
  onRenew: () => void;
  onBuy: () => void;
  onOpenAccess: () => void;
  onCopyReferral: () => void;
  onShareReferralToTelegram: () => void;
  onWithdraw: () => void;
  referralCopied: boolean;
}

export function HomePage({
  subscription,
  referralData,
  onActivateTrial,
  onRenew,
  onBuy,
  onOpenAccess,
  onCopyReferral,
  onShareReferralToTelegram,
  onWithdraw,
  referralCopied,
}: HomePageProps) {
  return (
    <div className="space-y-4 px-4 pb-20 pt-4">
      <SubscriptionCard
        subscription={subscription}
        onActivateTrial={onActivateTrial}
        onRenew={onRenew}
        onBuy={onBuy}
        onOpenAccess={onOpenAccess}
      />
      
      <ReferralCard
        referralCode={referralData.referralCode}
        referralsCount={referralData.referralsCount}
        referralEarnings={referralData.referralEarnings}
        availableForWithdraw={referralData.availableForWithdraw}
        onCopy={onCopyReferral}
        onShareTelegram={onShareReferralToTelegram}
        onWithdraw={onWithdraw}
        copied={referralCopied}
      />
    </div>
  );
}
