/**
 * Credits screen — balance, lifetime stats, and tier progress.
 */
import React, { useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { useAgentStore } from '../store/agentStore';

function ProgressBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min((value / Math.max(max, 1)) * 100, 100);
  return (
    <View style={styles.progressTrack}>
      <View style={[styles.progressFill, { width: `${pct}%` as any, backgroundColor: color }]} />
    </View>
  );
}

export function CreditsScreen() {
  const { credits, status, fetchStatus } = useAgentStore();

  useEffect(() => { fetchStatus(); }, []);

  const units = status?.total_compute_units ?? 0;

  // Tier progress
  const CONTRIBUTOR_THRESHOLD = 3600;
  const POWER_THRESHOLD = 72000;
  const nextTier = units < CONTRIBUTOR_THRESHOLD
    ? { name: 'Contributor', target: CONTRIBUTOR_THRESHOLD }
    : units < POWER_THRESHOLD
    ? { name: 'Power', target: POWER_THRESHOLD }
    : null;

  return (
    <ScrollView style={styles.container}>
      <View style={styles.balanceCard}>
        <Text style={styles.balanceLabel}>Available Credits</Text>
        <Text style={styles.balanceValue}>
          {credits ? credits.available.toFixed(0) : '—'}
        </Text>
        <Text style={styles.balanceSub}>
          ≈ {credits ? (credits.available / 60).toFixed(0) : '—'} minutes of GPU training
        </Text>
      </View>

      <View style={styles.statsRow}>
        <View style={styles.statBox}>
          <Text style={styles.statNum}>{credits?.lifetime_earned.toFixed(0) ?? '—'}</Text>
          <Text style={styles.statLbl}>Earned</Text>
        </View>
        <View style={styles.statBox}>
          <Text style={styles.statNum}>{credits?.lifetime_spent.toFixed(0) ?? '—'}</Text>
          <Text style={styles.statLbl}>Spent</Text>
        </View>
        <View style={styles.statBox}>
          <Text style={styles.statNum}>{units.toFixed(0)}</Text>
          <Text style={styles.statLbl}>Compute Units</Text>
        </View>
      </View>

      {nextTier && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Progress to {nextTier.name}</Text>
          <ProgressBar value={units} max={nextTier.target} color="#6C63FF" />
          <Text style={styles.progressText}>
            {units.toFixed(0)} / {nextTier.target.toLocaleString()} units
          </Text>
          <Text style={styles.progressHint}>
            Unlock higher GPU limits and priority scheduling
          </Text>
        </View>
      )}

      <View style={styles.card}>
        <Text style={styles.cardTitle}>How to earn more</Text>
        <Text style={styles.hint}>• Leave the app running in background</Text>
        <Text style={styles.hint}>• Connect a Mac mini to the network (+35% rate)</Text>
        <Text style={styles.hint}>• Keep device plugged in for uninterrupted sessions</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F0F1A', padding: 16 },
  balanceCard: {
    backgroundColor: '#1A1A2E', borderRadius: 16, padding: 24,
    alignItems: 'center', marginBottom: 16,
  },
  balanceLabel: { color: '#888', fontSize: 13 },
  balanceValue: { color: '#6C63FF', fontSize: 56, fontWeight: '800', marginVertical: 4 },
  balanceSub: { color: '#aaa', fontSize: 13 },
  statsRow: { flexDirection: 'row', gap: 12, marginBottom: 16 },
  statBox: {
    flex: 1, backgroundColor: '#1A1A2E', borderRadius: 12,
    padding: 14, alignItems: 'center',
  },
  statNum: { color: '#fff', fontSize: 20, fontWeight: '700' },
  statLbl: { color: '#666', fontSize: 11, marginTop: 4 },
  card: { backgroundColor: '#1A1A2E', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardTitle: { color: '#888', fontSize: 12, marginBottom: 12 },
  progressTrack: { height: 8, backgroundColor: '#2A2A3E', borderRadius: 4, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 4 },
  progressText: { color: '#ccc', fontSize: 12, marginTop: 6 },
  progressHint: { color: '#555', fontSize: 11, marginTop: 4 },
  hint: { color: '#ccc', fontSize: 14, lineHeight: 24 },
});
