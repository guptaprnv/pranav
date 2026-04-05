/**
 * Contribute screen — start/stop contributing compute,
 * shows real-time contribution rate and session stats.
 */
import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert } from 'react-native';
import { useAgentStore } from '../store/agentStore';

export function ContributeScreen() {
  const { status, fetchStatus, startContributing, stopContributing } = useAgentStore();
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    fetchStatus();
    const timer = setInterval(() => {
      setElapsed(e => e + 1);
      if (elapsed % 15 === 0) fetchStatus();
    }, 1000);
    return () => clearInterval(timer);
  }, [elapsed]);

  const toggle = async () => {
    setLoading(true);
    try {
      if (status?.running) {
        await stopContributing();
      } else {
        await startContributing();
      }
    } finally {
      setLoading(false);
    }
  };

  const isRunning = status?.running ?? false;
  const tier = status?.hardware_tier ?? 'unknown';
  // Estimated earn rate
  const TIER_RATES: Record<string, number> = {
    ipad_m2: 0.12, ipad_m1: 0.08, ipad_neural: 0.05,
    apple_m3: 0.35, apple_m2: 0.28, unknown: 0.10,
  };
  const ratePerMin = (TIER_RATES[tier] ?? 0.10) * 60;

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Your Device</Text>
        <Text style={styles.tier}>{tier.replace(/_/g, ' ').toUpperCase()}</Text>
        <Text style={styles.rate}>
          ~{ratePerMin.toFixed(1)} compute-units / minute
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>How it works</Text>
        <Text style={styles.explain}>
          When you contribute, your device processes model validation tasks.
          Every minute you contribute earns you compute-units which convert
          to training credits — spend them to train your own models.
        </Text>
        <Text style={styles.explain}>
          💡 Mac mini M3 earns {(0.35 * 60).toFixed(0)} units/min.{'\n'}
          iPad M2 earns {(0.12 * 60).toFixed(0)} units/min.
        </Text>
      </View>

      <TouchableOpacity
        style={[styles.button, isRunning ? styles.stopButton : styles.startButton]}
        onPress={toggle}
        disabled={loading}
      >
        <Text style={styles.buttonText}>
          {loading ? '…' : isRunning ? '■ Stop Contributing' : '▶ Start Contributing'}
        </Text>
      </TouchableOpacity>

      {isRunning && (
        <Text style={styles.sessionText}>
          Session active • {Math.floor(elapsed / 60)}m {elapsed % 60}s
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F0F1A', padding: 16 },
  card: { backgroundColor: '#1A1A2E', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardTitle: { color: '#888', fontSize: 12, marginBottom: 8 },
  tier: { color: '#6C63FF', fontSize: 22, fontWeight: '800', marginBottom: 4 },
  rate: { color: '#4CAF50', fontSize: 14 },
  explain: { color: '#ccc', fontSize: 14, lineHeight: 21, marginTop: 8 },
  button: {
    borderRadius: 14, padding: 18, alignItems: 'center', marginTop: 8,
  },
  startButton: { backgroundColor: '#6C63FF' },
  stopButton: { backgroundColor: '#C62828' },
  buttonText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  sessionText: { color: '#4CAF50', textAlign: 'center', marginTop: 12, fontSize: 14 },
});
