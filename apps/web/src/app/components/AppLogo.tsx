import React from 'react';

import appLogoUrl from '../../../../bot/bot/assets/menu/logo.jpg';

interface AppLogoProps {
  className?: string;
  imageClassName?: string;
  alt?: string;
  shape?: 'circle' | 'card';
}

export function AppLogo({
  className = '',
  imageClassName = '',
  alt = 'QuickVPN',
  shape = 'circle',
}: AppLogoProps) {
  const shapeClassName = shape === 'card' ? 'rounded-[24px]' : 'rounded-full';

  return (
    <div
      className={`flex items-center justify-center overflow-hidden bg-white ${shapeClassName} ${className}`.trim()}
    >
      <img
        src={appLogoUrl}
        alt={alt}
        className={`h-full w-full object-contain p-[10%] ${imageClassName}`.trim()}
      />
    </div>
  );
}
