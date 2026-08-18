import React, { useState, useEffect } from 'react';
import { view } from '@forge/bridge';

import { SquadReport } from './SquadReport';
import SubTaskRecommendation from './SubTaskRecommendation';

function App() {
  const [isReportPage, setIsReportPage] = useState(false);
  const [issueKey, setIssueKey] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  // ==========================================================
  // GET JIRA CONTEXT
  // ==========================================================

  useEffect(() => {
    async function loadContext() {
      try {
        if (view && view.theme) {
          view.theme.enable();
        }

        const context = await view.getContext();

        console.log('[App] Forge context:', context);

        if (!context) {
          setLoading(false);
          return;
        }

        const isProjectView =
          context.moduleKey === 'custom-reports-with-filter' ||
          context.moduleKey === 'squad-reporting-page' ||
          context.moduleKey === 'squad-report-page' ||
          context.extension?.type === 'jira:projectPage' ||
          !context.extension?.issue;

        if (isProjectView) {
          console.log('[App] Project page detected');
          setIsReportPage(true);
          setLoading(false);
          return;
        }

        if (context.extension?.issue) {
          const key = context.extension.issue.key;
          console.log('[App] Issue key:', key);
          setIssueKey(key);
          setLoading(false);
          return;
        }

        setLoading(false);
      } catch (error) {
        console.error('[App] Context error:', error);
        setErrorMsg('Tidak dapat membaca Jira issue context.');
        setLoading(false);
      }
    }

    loadContext();
  }, []);

  // ==========================================================
  // ROUTING
  // ==========================================================

  if (loading) {
    return (
      <div
        style={{
          padding: '20px',
          textAlign: 'center',
          fontSize: '13px',
          color: 'var(--ds-text-subtle, #5E6C84)',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        }}
      >
        Memuat info Epic...
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div
        style={{
          padding: '12px',
          fontSize: '12px',
          color: '#DE350B',
          backgroundColor: '#FFEBE6',
          borderRadius: '3px',
          margin: '12px',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        }}
      >
        {errorMsg}
      </div>
    );
  }

  if (isReportPage) {
    return <SquadReport />;
  }

  return <SubTaskRecommendation issueKey={issueKey} />;
}

export default App;