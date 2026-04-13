import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useLocale } from '../contexts/LocaleContext';
import ProfileViewer from '../components/harness/ProfileViewer';
import ShareManager from '../components/harness/ShareManager';
import ImportApply from '../components/harness/ImportApply';
import UploadWorkspace from '../components/harness/UploadWorkspace';
import ComposeWorkspace from '../components/harness/ComposeWorkspace';
import ShowcaseModal from '../components/harness/ShowcaseBar';

interface Profile { agent_id: string; product: string }

export default function HarnessPage() {
  const { t } = useLocale();
  const [profiles, setProfiles] = useState<Profile[]>([]);

  const refreshProfiles = useCallback(() => {
    api('/harness/profiles').then(d => setProfiles(d.data || [])).catch(() => {});
  }, []);

  useEffect(() => { refreshProfiles(); }, [refreshProfiles]);

  return (
    <div className="p-6 space-y-6 max-w-[1200px] mx-auto">
      <div className="w-full">
        <h1 className="text-3xl font-bold font-serif">{t('harness.title')}</h1>
        <p className="text-sm text-muted mt-2 leading-relaxed">
          {t('harness.intro')}{' '}<ShowcaseModal />
        </p>
      </div>

      <div className="space-y-6">
        <UploadWorkspace onUploaded={refreshProfiles} />
        <ProfileViewer profiles={profiles} onDeleted={refreshProfiles} />
        <ComposeWorkspace profiles={profiles} />
      </div>

      <hr className="border-border" />

      <div className="space-y-6">
        <ShareManager profiles={profiles} />
        <ImportApply />
      </div>
    </div>
  );
}
