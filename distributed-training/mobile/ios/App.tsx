/**
 * DTrain Node — iPad companion app
 *
 * Features:
 *  - Connects to the node agent running on the same device / local network
 *  - Shows contribution stats, credit balance, and peer map
 *  - Starts/stops compute contribution
 *  - Background fetch: keeps contribution session alive when app is backgrounded
 *
 * Architecture:
 *  - React Native (Expo) for cross-platform (iOS / iPadOS)
 *  - expo-background-fetch for continuous contribution when backgrounded
 *  - Connects to local node agent HTTP API (127.0.0.1:7777)
 *    OR remote API (api.dtrain.ai) when agent is running on a Mac mini
 */

import React, { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';

import { DashboardScreen } from './src/screens/DashboardScreen';
import { ContributeScreen } from './src/screens/ContributeScreen';
import { PeersScreen } from './src/screens/PeersScreen';
import { CreditsScreen } from './src/screens/CreditsScreen';
import { useAgentStore } from './src/store/agentStore';

const Tab = createBottomTabNavigator();
const BACKGROUND_FETCH_TASK = 'dt-heartbeat';

// Background heartbeat — keeps contribution session alive
TaskManager.defineTask(BACKGROUND_FETCH_TASK, async () => {
  try {
    const { agentUrl, sessionId } = useAgentStore.getState();
    if (sessionId) {
      await fetch(`${agentUrl}/heartbeat`, { method: 'POST' });
    }
    return BackgroundFetch.BackgroundFetchResult.NewData;
  } catch {
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

export default function App() {
  useEffect(() => {
    BackgroundFetch.registerTaskAsync(BACKGROUND_FETCH_TASK, {
      minimumInterval: 30,         // every 30 seconds
      stopOnTerminate: false,
      startOnBoot: false,
    }).catch(console.warn);
  }, []);

  return (
    <NavigationContainer>
      <StatusBar style="auto" />
      <Tab.Navigator
        screenOptions={{
          tabBarActiveTintColor: '#6C63FF',
          headerStyle: { backgroundColor: '#1A1A2E' },
          headerTintColor: '#fff',
        }}
      >
        <Tab.Screen
          name="Dashboard"
          component={DashboardScreen}
          options={{ tabBarLabel: 'Dashboard' }}
        />
        <Tab.Screen
          name="Contribute"
          component={ContributeScreen}
          options={{ tabBarLabel: 'Contribute' }}
        />
        <Tab.Screen
          name="Peers"
          component={PeersScreen}
          options={{ tabBarLabel: 'Network' }}
        />
        <Tab.Screen
          name="Credits"
          component={CreditsScreen}
          options={{ tabBarLabel: 'Credits' }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
