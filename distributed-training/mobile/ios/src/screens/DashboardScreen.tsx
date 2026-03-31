/**
 * Dashboard — main screen showing agent status and contribution summary.
 */
import React, { useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView,
  RefreshControl, ActivityIndicator,
} from 'react-native';
import { useAgentStore } from '../store/agentStore';

function TierBadge({ units }: { units: number }) {
  const tier = units >= 72000 ? 'Power ⚡' : units >= 3600 ? 'Contributor ★' : 'Free ☆';
  const color = units >= 72000 ? '#FFD700' : units >= 3600 ? '#6C63FF' : '#888';
  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <Text style={[styles.badgeText, { color }]}>{tier}</Text>
    </View>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <View style={styles.statCard}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
      {sub ? <Text style={styles.statSub}>{sub}</Text> : null}
    </View>
  );
}

export function DashboardScreen() {
  const { status, credits, error, fetchStatus } = useAgentStore();
  const [refreshing, setRefreshing] = React.useState(false);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchStatus();
    setRefreshing(false);
  }, [fetchStatus]);

  if (!status && !error) {
    return <ActivityIndicator style={{ flex: 1 }} color="#6C63FF" />;
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      {error ? (
        <View style={styles.errorCard}>
          <Text style={styles.errorText}>⚠ Agent offline</Text>
          <Text style={styles.errorSub}>{error}</Text>
        </View>
      ) : null}

      {status ? (
        <>
          <View style={styles.header}>
            <Text style={styles.ownerText}>{status.owner}</Text>
            <TierBadge units={status.total_compute_units} />
            <View style={[styles.dot, { backgroundColor: status.running ? '#4CAF50' : '#888' }]} />
            <Text style={styles.runningText}>{status.running ? 'Active' : 'Stopped'}</Text>
          </View>

          <View style={styles.statsGrid}>
            <StatCard
              label="Compute Units"
              value={status.total_compute_units.toFixed(1)}
              sub="earned lifetime"
            />
            <StatCard
              label="Credits"
              value={credits ? credits.available.toFixed(0) : '—'}
              sub="available"
            />
            <StatCard label="Peers" value={String(status.peers_known)} sub="online" />
            <StatCard
              label="Device"
              value={status.hardware_tier.replace('_', ' ')}
              sub={status.device_type}
            />
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Gossip Round</Text>
            <Text style={styles.sectionValue}>#{status.gossip_round}</Text>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Peer ID</Text>
            <Text style={styles.sectionValue}>{status.peer_id.slice(0, 16)}…</Text>
          </View>
        </>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F0F1A', padding: 16 },
  header: { flexDirection: 'row', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 8 },
  ownerText: { color: '#fff', fontSize: 20, fontWeight: '700', flex: 1 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  runningText: { color: '#aaa', fontSize: 14 },
  badge: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3 },
  badgeText: { fontSize: 12, fontWeight: '600' },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 },
  statCard: {
    backgroundColor: '#1A1A2E', borderRadius: 12, padding: 16,
    minWidth: '45%', flex: 1, alignItems: 'center',
  },
  statValue: { color: '#6C63FF', fontSize: 28, fontWeight: '800' },
  statLabel: { color: '#ccc', fontSize: 12, marginTop: 4 },
  statSub: { color: '#666', fontSize: 11 },
  section: { backgroundColor: '#1A1A2E', borderRadius: 12, padding: 16, marginBottom: 12 },
  sectionTitle: { color: '#888', fontSize: 12, marginBottom: 4 },
  sectionValue: { color: '#fff', fontSize: 16, fontFamily: 'monospace' },
  errorCard: { backgroundColor: '#2D1B1B', borderRadius: 12, padding: 16, marginBottom: 16 },
  errorText: { color: '#FF6B6B', fontSize: 16, fontWeight: '600' },
  errorSub: { color: '#aaa', fontSize: 12, marginTop: 4 },
});
