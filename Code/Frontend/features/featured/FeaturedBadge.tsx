'use client';

import { useT } from '@/lib/i18n';
import { Icon } from '@/components/icon';
import styles from './featured.module.css';

export function FeaturedBadge() {
  const t = useT();
  return (
    <span className={styles.badge}>
      <Icon name="star"/>
      {t('Featured')}
    </span>
  );
}
