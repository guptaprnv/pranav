/**
 * Peers screen — shows the live P2P network map.
 */
import React, { useEffect } from 'react';
import { View, Text, FlatList, StyleSheet, RefreshControl } from 'react-native';
import { useAgentStore } from '../store/agentStore';

function PeerRow({ peer }: { peer: any }) {
  const gpuLabel = peer.gpu_count > 0 ? `${peer.gpu_count} GPU` : 'CPU';
  const online = (Date.now() / 1000 - peer.last_seen) < 120;
  return (
    <View style={styles.row}>
      <View style={[styles.dot, { backgroundColor: online ? '#4CAF50' : '#555' }]} />
      <View style={{ flex: 1 }}>
        <Text style={styles.peerId}>{peer.peer_id?.slice(0, 12)}…</Text>
        <Text style={styles.peerMeta}>
          {peer.device_type} • {gpuLabel} • {peer.memory_gb}GB
        </Text>
      </View>
      <Text style={styles.contribution}>
        {peer.contribution_score?.toFixed(0) ?? 0} pts
      </Text>
    </View>
  );
}

export function PeersScreen() {
  const { peers, fetchStatus } = useAgentStore();
  const [refreshing, setRefreshing] = React.useState(false);

  useEffect(() => { fetchStatus(); }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchStatus();
    setRefreshing(false);
  };

  return (
    <View style={styles.container}>
      <Text style={styles.header}>{peers.length} peers online</Text>
      <FlatList
        data={peers}
        keyExtractor={p => p.peer_id}
        renderItem={({ item }) => <PeerRow peer={item} />}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        ListEmptyComponent={
          <Text style={styles.empty}>No peers found. Make sure your agent is running.</Text>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F0F1A', padding: 16 },
  header: { color: '#888', fontSize: 13, marginBottom: 12 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: '#1A1A2E', borderRadius: 10, padding: 14, marginBottom: 10,
  },
  dot: { width: 10, height: 10, borderRadius: 5 },
  peerId: { color: '#fff', fontSize: 14, fontFamily: 'monospace' },
  peerMeta: { color: '#888', fontSize: 12, marginTop: 2 },
  contribution: { color: '#6C63FF', fontSize: 14, fontWeight: '700' },
  empty: { color: '#555', textAlign: 'center', marginTop: 60, fontSize: 15 },
});
