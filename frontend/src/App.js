import React, { useState, useEffect, useCallback } from 'react';
import { view, events } from '@forge/bridge';

import { SquadReport } from './SquadReport';
import SubTaskRecommendation from './SubTaskRecommendation';

function App() {
  const [isReportPage, setIsReportPage] = useState(false);
  const [issueKey, setIssueKey] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  // ==========================================================
  // GET JIRA CONTEXT WITH TIMEOUT & RETRY
  // ==========================================================

  const loadContext = useCallback(async (retriesLeft = 3) => {
    setLoading(true);
    setErrorMsg('');

    try {
      if (view && view.theme) {
        try {
          await view.theme.enable();
        } catch (e) {
          console.warn('[App] Theme enable warning:', e);
        }
      }

      // Timeout 4 detik agar tidak menggantung tanpa kejelasan
      const contextPromise = view.getContext();
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Bridge getContext timeout')), 4000)
      );

      const context = await Promise.race([contextPromise, timeoutPromise]);
      console.log('[App] Forge context loaded:', context);

      if (!context) {
        throw new Error('Context response empty');
      }

      const isProjectView =
        context.moduleKey === 'custom-reports-with-filter' ||
        context.moduleKey === 'squad-reporting-page' ||
        context.moduleKey === 'squad-report-page' ||
        context.extension?.type === 'jira:projectPage';

      if (isProjectView) {
        console.log('[App] Project page view detected');
        setIsReportPage(true);
        setLoading(false);
        return;
      }

      const key =
        context.extension?.issue?.key ||
        context.extension?.issueKey ||
        context.extension?.issue?.id ||
        context.issueKey;

      if (key) {
        console.log('[App] Issue key detected:', key);
        setIssueKey(key);
        setIsReportPage(false);
        setLoading(false);
      } else {
        console.warn('[App] Context does not contain issue key, defaulting to issue panel view:', context);
        setIsReportPage(false);
        setLoading(false);
      }
    } catch (error) {
        console.warn(`[App] Context load attempt failed (${retriesLeft} retries left):`, error);
        if (retriesLeft > 0) {
          setTimeout(() => loadContext(retriesLeft - 1), 1000);
        } else {
          const isStandalone = window.self === window.top;
          if (isStandalone) {
            setErrorMsg(
              'Aplikasi Forge Custom UI ini harus dibuka di dalam Jira Cloud (bukan di browser standalone/localhost).'
            );
          } else {
            setErrorMsg(
              'Gagal terhubung dengan Jira Bridge. Pastikan "forge tunnel" aktif di terminal jika dalam mode pengembangan.'
            );
          }
          setLoading(false);
        }
    }
  }, []);

  useEffect(() => {
    loadContext(3);

    // Listen to live issue change events if available
    let unsubscribe = null;
    try {
      if (events && typeof events.on === 'function') {
        unsubscribe = events.on('JIRA_ISSUE_CHANGED', (data) => {
          console.log('[App] JIRA_ISSUE_CHANGED event received:', data);
          if (data?.issue?.key) {
            setIssueKey(data.issue.key);
            setErrorMsg('');
            setLoading(false);
          }
        });
      }
    } catch (e) {
      console.warn('[App] Listening to JIRA_ISSUE_CHANGED failed:', e);
    }

    return () => {
      if (unsubscribe && typeof unsubscribe === 'function') {
        try {
          unsubscribe();
        } catch (e) {}
      }
    };
  }, [loadContext]);

  // ==========================================================
  // ROUTING & UI RENDER
  // ==========================================================

  if (loading) {
    return (
      <div
        style={{
          padding: '24px',
          textAlign: 'center',
          fontSize: '13px',
          color: 'var(--ds-text-subtle, #5E6C84)',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        }}
      >
        <div style={{ marginBottom: '8px', fontWeight: 600 }}>Memuat Jira Context...</div>
        <div style={{ fontSize: '11px', color: '#8993A4' }}>Menghubungkan aplikasi ke Atlassian Forge Bridge</div>
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div
        style={{
          padding: '16px',
          fontSize: '13px',
          color: '#DE350B',
          backgroundColor: '#FFEBE6',
          border: '1px solid #FFBDAD',
          borderRadius: '4px',
          margin: '16px',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: '6px' }}>⚠️ Kendala Koneksi Context Jira</div>
        <div style={{ marginBottom: '12px', lineHeight: '1.4' }}>{errorMsg}</div>
        
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            onClick={() => loadContext(3)}
            style={{
              padding: '6px 12px',
              backgroundColor: '#DE350B',
              color: '#FFFFFF',
              border: 'none',
              borderRadius: '3px',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '12px',
            }}
          >
            🔄 Coba Lagi
          </button>
          
          <button
            onClick={() => {
              setErrorMsg('');
              setIsReportPage(true);
            }}
            style={{
              padding: '6px 12px',
              backgroundColor: '#FFFFFF',
              color: '#42526E',
              border: '1px solid #DFE1E6',
              borderRadius: '3px',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '12px',
            }}
          >
            📊 Buka Reports Overview
          </button>
        </div>
      </div>
    );
  }

  if (isReportPage) {
    return <SquadReport />;
  }

  return <SubTaskRecommendation issueKey={issueKey} />;
}

export default App;