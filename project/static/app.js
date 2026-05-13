const API = {
    async getCases() {
        const res = await fetch('/api/cases');
        return res.json();
    },
    async createCase(caseName) {
        const res = await fetch('/api/cases', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_name: caseName }),
        });
        return res.json();
    },
    async getRecords(params) {
        const qs = new URLSearchParams(params).toString();
        const res = await fetch(`/api/records?${qs}`);
        return res.json();
    },
    async getRecord(caseId, recordId) {
        const res = await fetch(`/api/record/${recordId}?case=${caseId}`);
        return res.json();
    },
    async search(caseId, keyword) {
        const res = await fetch(`/api/search?case=${caseId}&keyword=${encodeURIComponent(keyword)}`);
        return res.json();
    },
    async getFilters(caseId, extraParams = {}) {
        const qs = new URLSearchParams({ case: caseId, ...extraParams }).toString();
        const res = await fetch(`/api/filters?${qs}`);
        return res.json();
    },
    async getSummaries(caseId) {
        const res = await fetch(`/api/summaries?case=${caseId}`);
        return res.json();
    },
    async getPersonSummaries(caseId) {
        const res = await fetch(`/api/person-summaries?case=${caseId}`);
        return res.json();
    },
    async getIndictment(caseId) {
        const res = await fetch(`/api/indictment?case=${caseId}`);
        return res.json();
    },
    async getPartyContext(caseId) {
        const res = await fetch(`/api/parties?case=${caseId}`);
        return res.json();
    },
    async getPartyCandidates(caseId, query = '') {
        const qs = new URLSearchParams({ case: caseId });
        if (query) qs.set('q', query);
        const res = await fetch(`/api/parties/candidates?${qs.toString()}`);
        return res.json();
    },
    async savePartyContext(caseId, entrustedParties, relatedPeople) {
        const res = await fetch('/api/parties', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                case: caseId,
                entrusted_parties: entrustedParties,
                related_people: relatedPeople,
            }),
        });
        return res.json();
    },
    async getGraph(caseId) {
        const res = await fetch(`/api/graph?case=${caseId}`);
        return res.json();
    },
    getDrawioUrl(caseId) {
        return `/api/graph/drawio?case=${encodeURIComponent(caseId)}`;
    },
    async getAISettings() {
        const res = await fetch('/api/ai/settings');
        return res.json();
    },
    async saveAISettings(payload) {
        const res = await fetch('/api/ai/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        return res.json();
    },
    async testAI(profile, config) {
        const res = await fetch('/api/ai/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile, config }),
        });
        return res.json();
    },
    async getJobs(caseId) {
        const res = await fetch(`/api/jobs?case=${encodeURIComponent(caseId)}`);
        return res.json();
    },
    async confirmClient(caseId, name) {
        const resp = await fetch(`/api/cases/${encodeURIComponent(caseId)}/confirm-client`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name}),
        });
        return resp.json();
    },
    async getJob(caseId, jobId) {
        const resp = await fetch(`/api/jobs/${encodeURIComponent(jobId)}?case=${encodeURIComponent(caseId)}`);
        return resp.json();
    },
    async getManifest(caseId, jobId) {
        const resp = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/manifest?case=${encodeURIComponent(caseId)}`);
        return resp.json();
    },
    async getJobManifest(caseId, jobId) {
        const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/manifest?case=${encodeURIComponent(caseId)}`);
        return res.json();
    },
    getJobManifestDownloadUrl(caseId, jobId) {
        return `/api/jobs/${encodeURIComponent(jobId)}/manifest/download?case=${encodeURIComponent(caseId)}`;
    },
    getJobArtifactUrl(caseId, jobId, kind) {
        return `/api/jobs/${encodeURIComponent(jobId)}/artifact?case=${encodeURIComponent(caseId)}&kind=${encodeURIComponent(kind)}`;
    },
    async getJobArtifactPreview(caseId, jobId, kind) {
        const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/artifact/preview?case=${encodeURIComponent(caseId)}&kind=${encodeURIComponent(kind)}`);
        return res.json();
    },
    async openJobOutput(caseId, jobId) {
        const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/open-output?case=${encodeURIComponent(caseId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        return res.json();
    },
    async getGraphRAGIndex(caseId) {
        const res = await fetch(`/api/graphrag/index?case=${encodeURIComponent(caseId)}`);
        return res.json();
    },
    async rebuildGraphRAG(caseId) {
        const res = await fetch('/api/graphrag/rebuild', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case: caseId }),
        });
        return res.json();
    },
    async retrieveGraphRAG(caseId, query, limit = 5) {
        const res = await fetch('/api/graphrag/retrieve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case: caseId, query, limit }),
        });
        return res.json();
    },
    async pickFile(kind = '') {
        const res = await fetch('/api/system/pick-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind }),
        });
        return res.json();
    },
    async pickDirectory() {
        const res = await fetch('/api/system/pick-directory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        return res.json();
    },
    async startJob(caseId, type, params = {}) {
        const res = await fetch('/api/jobs/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case: caseId, type, params }),
        });
        return res.json();
    },
    async startAutoMaterialBuild(caseId, params = {}) {
        return this.startJob(caseId, 'material_auto_build', params);
    },
    async getChatHistory(caseId) {
        const res = await fetch(`/api/chat/history?case=${encodeURIComponent(caseId)}`);
        return res.json();
    },
    async sendChat(caseId, message, profile) {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case: caseId, message, profile }),
        });
        return res.json();
    },
    /**
     * SSE 流式聊天 — 返回一个可取消的控制器。
     * 用法：
     *   const ctrl = API.sendChatStream(caseId, message, profile, {
     *       onStage(stage)   { ... },   // { stage, text, count? }
     *       onToken(text)    { ... },
     *       onDone(payload)  { ... },   // { memory_note, parse_entries }
     *       onError(msg)     { ... },
     *   });
     *   ctrl.abort();  // 取消
     */
    sendChatStream(caseId, message, profile, callbacks) {
        const abortCtrl = new AbortController();
        const signal = abortCtrl.signal;
        const url = '/api/chat/stream';
        let aborted = false;

        (async () => {
            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ case: caseId, message, profile }),
                    signal,
                });
                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    callbacks.onError(errData.error || `HTTP ${res.status}`);
                    return;
                }
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let eventType = '';
                let eventData = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';  // 保留不完整行

                    for (const line of lines) {
                        if (aborted) return;
                        if (line.startsWith('event: ')) {
                            eventType = line.slice(7).trim();
                        } else if (line.startsWith('data: ')) {
                            eventData = line.slice(6).trim();
                        } else if (line === '' && eventType && eventData) {
                            // 完整事件
                            let data;
                            try { data = JSON.parse(eventData); } catch (e) { data = {}; }
                            switch (eventType) {
                                case 'stage':
                                    callbacks.onStage(data);
                                    break;
                                case 'token':
                                    callbacks.onToken(data.content || '');
                                    break;
                                case 'done':
                                    callbacks.onDone(data);
                                    return;
                                case 'error':
                                    callbacks.onError(data.text || '未知错误');
                                    return;
                            }
                            eventType = '';
                            eventData = '';
                        }
                    }
                }
                // 流结束但没有 done 事件 — 视为完成
                if (!aborted) callbacks.onDone({});
            } catch (e) {
                if (e.name === 'AbortError') return;
                callbacks.onError(e.message || '连接异常');
            }
        })();

        return {
            abort() { aborted = true; abortCtrl.abort(); },
        };
    },
    async saveAgentResult(caseId, title, format, content) {
        const res = await fetch('/api/agent/save-result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case: caseId, title, format, content }),
        });
        return res.json();
    },
    async deleteCase(caseId) {
        const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}`, { method: 'DELETE' });
        return res.json();
    },
    async restoreCase(caseId) {
        const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/restore`, { method: 'POST' });
        return res.json();
    },
    async getTrash() {
        const res = await fetch('/api/trash');
        return res.json();
    },
    async emptyTrash() {
        const res = await fetch('/api/trash/empty', { method: 'POST' });
        return res.json();
    },
    async permanentDeleteTrash(caseId) {
        const res = await fetch(`/api/trash/${encodeURIComponent(caseId)}`, { method: 'DELETE' });
        return res.json();
    },
    async updateCaseField(caseId, field, key, content) {
        const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/update-field`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ field, key, content }),
        });
        return res.json();
    },
    async openWorkspace() {
        const res = await fetch('/api/workspace/open', { method: 'POST' });
        return res.json();
    },
};

const TRASH_DAYS = 7;

const state = {
    cases: [],
    hasEnteredWorkspace: false,
    currentCase: null,
    records: [],
    isSearchMode: false,
    searchKeywords: [],
    isSearching: false,
    currentView: 'records',
    summaries: {},
    personSummaries: {},
    indictment: null,
    graph: null,
    partyContext: null,
    graphMode: 'mindmap',
    selectedParties: [],
    graphSimulation: null,
    aiSettings: null,
    graphragStatus: null,
    graphragRetrieval: null,
    chatMessages: [],
    partyCandidates: [],
};

// DOM elements
const dom = {
    appShell: document.getElementById('app-shell'),
    caseEntryCover: document.getElementById('case-entry-cover'),
    btnEntryNewCase: document.getElementById('btn-entry-new-case'),
    btnEntryOldCase: document.getElementById('btn-entry-old-case'),
    entryOldPanel: document.getElementById('entry-old-panel'),
    entryNewPanel: document.getElementById('entry-new-panel'),
    entryCaseList: document.getElementById('entry-case-list'),
    entryTrashPanel: document.getElementById('entry-trash-panel'),
    entryTrashList: document.getElementById('entry-trash-list'),
    btnOpenTrash: document.getElementById('btn-open-trash'),
    btnBackFromTrash: document.getElementById('btn-back-from-trash'),
    btnEmptyTrash: document.getElementById('btn-empty-trash'),
    newCaseName: document.getElementById('new-case-name'),
    newCaseUseExistingConfig: document.getElementById('new-case-use-existing-config'),
    newCaseConfigFields: document.getElementById('new-case-config-fields'),
    newStrongBaseUrl: document.getElementById('new-strong-base-url'),
    newStrongModel: document.getElementById('new-strong-model'),
    newStrongApiKey: document.getElementById('new-strong-api-key'),
    newCheapBaseUrl: document.getElementById('new-cheap-base-url'),
    newCheapModel: document.getElementById('new-cheap-model'),
    newCheapApiKey: document.getElementById('new-cheap-api-key'),
    newMineruApiToken: document.getElementById('new-mineru-api-token'),
    newCaseRawPdf: document.getElementById('new-case-raw-pdf'),
    newDocumentType: document.getElementById('new-document-type'),
    newDocumentPdf: document.getElementById('new-document-pdf'),
    newClientName: document.getElementById('new-client-name'),
    newClientCandidates: document.getElementById('new-client-candidates'),
    newClientCandidateList: document.getElementById('new-client-candidate-list'),
    btnPickNewCasePdf: document.getElementById('btn-pick-new-case-pdf'),
    btnPickNewDocumentPdf: document.getElementById('btn-pick-new-document-pdf'),
    btnCreateCaseStartBuild: document.getElementById('btn-create-case-start-build'),
    caseSelect: document.getElementById('case-select'),
    recordCount: document.getElementById('record-count'),
    filterName: document.getElementById('filter-name'),
    filterType: document.getElementById('filter-type'),
    filterDate: document.getElementById('filter-date'),
    btnReset: document.getElementById('btn-reset'),
    searchInput: document.getElementById('search-input'),
    btnSearch: document.getElementById('btn-search'),
    searchBtnText: document.querySelector('.search-btn-text'),
    searchBtnLoading: document.querySelector('.search-btn-loading'),
    searchStats: document.getElementById('search-stats'),
    btnToggleFilters: document.getElementById('btn-toggle-filters'),
    filtersPanel: document.querySelector('.filters'),
    statusBar: document.getElementById('status-bar'),
    recordList: document.getElementById('record-list'),
    modal: document.getElementById('modal'),
    modalTitle: document.getElementById('modal-title'),
    modalCitationText: document.getElementById('modal-citation-text'),
    modalContent: document.getElementById('modal-content'),
    modalClose: document.getElementById('modal-close'),
    btnCopy: document.getElementById('btn-copy'),
    viewTabs: document.getElementById('view-tabs'),
    searchHero: document.getElementById('search-hero'),
    viewRecords: document.getElementById('view-records'),
    viewPersons: document.getElementById('view-persons'),
    viewGraph: document.getElementById('view-graph'),
    viewIndictment: document.getElementById('view-indictment'),
    viewAi: document.getElementById('view-ai'),
    viewEvidence: document.getElementById('view-evidence'),
    workflowPanel: document.getElementById('workflow-panel'),
    btnOpenCaseSetup: document.getElementById('btn-open-case-setup'),
    btnOpenNewCase: document.getElementById('btn-open-new-case'),
    btnCloseCaseSetup: document.getElementById('btn-close-case-setup'),
    caseContextClient: document.getElementById('case-context-client'),
    caseContextStatus: document.getElementById('case-context-status'),
    btnSavePartyContext: document.getElementById('btn-save-party-context'),
    partyContextOptions: document.getElementById('party-context-options'),
    partyContextCurrent: document.getElementById('party-context-current'),
    partyContextRelated: document.getElementById('party-context-related'),
    partyContextSummary: document.getElementById('party-context-summary'),
    personsStatusBar: document.getElementById('persons-status-bar'),
    personList: document.getElementById('person-list'),
    graphSidebar: document.getElementById('graph-sidebar'),
    graphContainer: document.getElementById('graph-container'),
    graphEmpty: document.getElementById('graph-empty'),
    graphModeSwitch: document.querySelector('.graph-mode-switch'),
    btnExportDrawio: document.getElementById('btn-export-drawio'),
    partyList: document.getElementById('party-list'),
    btnSelectAllParties: document.getElementById('btn-select-all-parties'),
    indictmentContainer: document.getElementById('indictment-container'),
    indictmentEmpty: document.getElementById('indictment-empty'),
    indictmentContent: document.getElementById('indictment-content'),
    indictmentStructured: document.getElementById('indictment-structured'),
    indictmentOriginal: document.getElementById('indictment-original'),
    btnToggleOriginal: document.getElementById('btn-toggle-original'),
    toggleOriginalText: document.getElementById('toggle-original-text'),
    modalAiSummary: document.getElementById('modal-ai-summary'),
    modalAiSummaryText: document.getElementById('modal-ai-summary-text'),
    btnSaveAISettings: document.getElementById('btn-save-ai-settings'),
    btnTestStrongAI: document.getElementById('btn-test-strong-ai'),
    btnTestCheapAI: document.getElementById('btn-test-cheap-ai'),
    strongProtocol: document.getElementById('strong-protocol'),
    strongBaseUrl: document.getElementById('strong-base-url'),
    strongModel: document.getElementById('strong-model'),
    strongApiKey: document.getElementById('strong-api-key'),
    cheapProtocol: document.getElementById('cheap-protocol'),
    cheapBaseUrl: document.getElementById('cheap-base-url'),
    cheapModel: document.getElementById('cheap-model'),
    cheapApiKey: document.getElementById('cheap-api-key'),
    routeChatDefault: document.getElementById('route-chat-default'),
    routeExtractDefault: document.getElementById('route-extract-default'),
    routeReviewDefault: document.getElementById('route-review-default'),
    mineruApiToken: document.getElementById('mineru-api-token'),
    mineruPollInterval: document.getElementById('mineru-poll-interval'),
    mineruTimeout: document.getElementById('mineru-timeout'),
    btnRebuildGraphRAG: document.getElementById('btn-rebuild-graphrag'),
    btnTestGraphRAG: document.getElementById('btn-test-graphrag'),
    graphragStatus: document.getElementById('graphrag-status'),
    graphragQuery: document.getElementById('graphrag-query'),
    graphragResults: document.getElementById('graphrag-results'),
    chatProfile: document.getElementById('chat-profile'),
    chatMessages: document.getElementById('chat-messages'),
    chatInput: document.getElementById('chat-input'),
    btnSendChat: document.getElementById('btn-send-chat'),
    companionToggle: document.getElementById('companion-toggle'),
    companionPanel: document.getElementById('companion-panel'),
    companionWidget: document.getElementById('companion-widget'),
    companionClose: document.getElementById('companion-close'),
    companionProfile: document.getElementById('companion-profile'),
    companionMessages: document.getElementById('companion-messages'),
    companionInput: document.getElementById('companion-input'),
    btnCompanionSend: document.getElementById('btn-companion-send'),
    btnBackToEntry: document.getElementById('btn-back-to-entry'),
    companionHint: document.getElementById('companion-hint'),
    btnOpenWorkspace: document.getElementById('btn-open-workspace'),
    entryBuildProgress: document.getElementById('entry-build-progress'),
    buildProgressFill: document.getElementById('build-progress-fill'),
    buildProgressStage: document.getElementById('build-progress-stage'),
    buildProgressDetail: document.getElementById('build-progress-detail'),
    entryClientSelect: document.getElementById('entry-client-select'),
    clientCandidateChips: document.getElementById('client-candidate-chips'),
    confirmClientName: document.getElementById('confirm-client-name'),
    confirmClientDatalist: document.getElementById('confirm-client-datalist'),
    btnConfirmClient: document.getElementById('btn-confirm-client'),
    entryAnalysisProgress: document.getElementById('entry-analysis-progress'),
    analysisSteps: document.querySelector('.analysis-steps'),
    btnEnterWorkbench: document.getElementById('btn-enter-workbench'),
};

// 初始化
async function init() {
    await refreshCaseOptions();
    await loadAISettings();
    bindEvents();

    // 刷新后恢复建库进度条（优先 sessionStorage，其次扫描 running job）
    let resumeCaseId, resumeJobId;
    try { resumeCaseId = sessionStorage.getItem('buildProgressCaseId'); } catch (_) {}
    try { resumeJobId = sessionStorage.getItem('buildProgressJobId'); } catch (_) {}
    if (!resumeJobId) {
        // sessionStorage 没记录时，从 API 查运行中的 material_auto_build 任务
        try {
            const resp = await fetch('/api/jobs');
            const data = await resp.json();
            const jobs = data.jobs || [];
            const running = jobs.find(j => j.type === 'material_auto_build' && j.status === 'running');
            if (running) {
                resumeCaseId = running.case;
                resumeJobId = running.id;
                try { sessionStorage.setItem('buildProgressCaseId', resumeCaseId); } catch (_) {}
                try { sessionStorage.setItem('buildProgressJobId', resumeJobId); } catch (_) {}
            }
        } catch (_) {}
    }
    if (resumeCaseId && resumeJobId) {
        try {
            // 先确认 job 在 store 中存在且状态匹配，再读 manifest
            const jobData = await API.getJob(resumeCaseId, resumeJobId);
            const job = jobData.job || jobData;
            if (job && (job.status === 'running' || job.status === 'completed')) {
                showEntryCover('new');
                showBuildProgress(resumeCaseId, resumeJobId);
                return;
            }
        } catch (_) {}
        try { sessionStorage.removeItem('buildProgressCaseId'); } catch (_) {}
        try { sessionStorage.removeItem('buildProgressJobId'); } catch (_) {}
    }

    showEntryCover();
}

async function refreshCaseOptions() {
    const cases = await API.getCases();
    state.cases = cases || [];
    refreshCaseSelector();
    renderEntryCaseList();
    return state.cases;
}

function refreshCaseSelector() {
    if (!dom.caseSelect) return;
    dom.caseSelect.innerHTML = (state.cases || []).map(c =>
        `<option value="${escapeAttr(c.id)}">${escapeHtml(c.name)} (${Number(c.record_count || 0)}份)</option>`
    ).join('');
    // 保持当前选中项
    if (state.currentCase) {
        dom.caseSelect.value = state.currentCase;
    }
}

function showEntryCover(mode = '') {
    state.hasEnteredWorkspace = false;
    dom.caseEntryCover.classList.remove('hidden');
    dom.appShell.classList.add('hidden');
    dom.entryOldPanel.classList.toggle('hidden', mode !== 'old');
    dom.entryNewPanel.classList.toggle('hidden', mode !== 'new');
}

async function enterExistingCase(caseId) {
    if (!caseId) {
        showToast('请先选择案件');
        return;
    }
    state.hasEnteredWorkspace = true;
    dom.caseEntryCover.classList.add('hidden');
    dom.appShell.classList.remove('hidden');
    dom.caseSelect.value = caseId;
    await loadCase(caseId);
}

function renderEntryCaseList() {
    if (!dom.entryCaseList) return;
    if (!state.cases.length) {
        dom.entryCaseList.innerHTML = '<div class="entry-empty">还没有案件。可以先建立新案件。</div>';
        return;
    }
    dom.entryCaseList.innerHTML = state.cases.map(item => `
        <div class="entry-case-row">
            <button class="entry-case-item" type="button" data-entry-case="${escapeAttr(item.id)}">
                <span>${escapeHtml(item.name || item.id)}</span>
                <small>${Number(item.record_count || 0)} 份笔录 · ${escapeHtml(item.filename || '')}</small>
            </button>
            <button class="entry-case-delete" type="button" data-delete-case="${escapeAttr(item.id)}" title="删除">✕</button>
        </div>
    `).join('');

    dom.entryCaseList.querySelectorAll('.entry-case-delete').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            deleteCase(btn.dataset.deleteCase);
        });
    });
}

async function deleteCase(caseId) {
    const item = state.cases.find(c => c.id === caseId);
    const name = item ? (item.name || item.id) : caseId;
    if (!confirm(`确定删除案件"${name}"？\n\n删除后可在废纸篓中保留 ${TRASH_DAYS} 天，过期自动彻底删除。`)) return;
    try {
        const data = await API.deleteCase(caseId);
        if (data.error) { showToast(data.error); return; }
        showToast(`"${name}" 已移入废纸篓`);
        state.cases = await API.getCases();
        refreshCaseSelector();
        renderEntryCaseList();
    } catch (e) {
        showToast('删除失败');
    }
}

async function openTrash() {
    dom.entryOldPanel.classList.add('hidden');
    dom.entryTrashPanel.classList.remove('hidden');
    await loadTrash();
}

function renderTrashList() {
    if (!dom.entryTrashList) return;
    state.trash = state.trash || [];
    if (!state.trash.length) {
        dom.entryTrashList.innerHTML = '<div class="entry-empty">废纸篓为空。</div>';
        return;
    }
    dom.entryTrashList.innerHTML = state.trash.map(item => `
        <div class="entry-case-row">
            <div class="entry-case-item trash-item">
                <span>${escapeHtml(item.case_name)}</span>
                <small>${escapeHtml(item.deleted_at)} · ${item.days_left} 天后彻底删除</small>
            </div>
            <button class="entry-case-restore" type="button" data-restore-case="${escapeAttr(item.case_id)}" title="恢复">↩</button>
            <button class="entry-case-delete-permanent" type="button" data-delete-permanent="${escapeAttr(item.case_id)}" title="彻底删除">✕</button>
        </div>
    `).join('');

    dom.entryTrashList.querySelectorAll('.entry-case-restore').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            restoreCase(btn.dataset.restoreCase);
        });
    });
    dom.entryTrashList.querySelectorAll('.entry-case-delete-permanent').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            permanentDeleteFromTrash(btn.dataset.deletePermanent);
        });
    });
}

async function restoreCase(caseId) {
    try {
        const data = await API.restoreCase(caseId);
        if (data.error) { showToast(data.error); return; }
        showToast('案件已恢复');
        state.cases = await API.getCases();
        refreshCaseSelector();
        state.trash = (await API.getTrash()).trash || [];
        renderEntryCaseList();
        renderTrashList();
    } catch (e) {
        showToast('恢复失败');
    }
}

function showConfirm(message) {
    return new Promise(resolve => {
        const overlay = document.getElementById('confirm-modal');
        const msgEl = document.getElementById('confirm-message');
        const btnCancel = document.getElementById('confirm-cancel');
        const btnOk = document.getElementById('confirm-ok');
        if (!overlay || !msgEl) { resolve(confirm(message)); return; }

        msgEl.textContent = message;
        overlay.classList.remove('hidden');

        function cleanup(result) {
            overlay.classList.add('hidden');
            btnCancel.removeEventListener('click', onCancel);
            btnOk.removeEventListener('click', onOk);
            document.removeEventListener('keydown', onKey);
            resolve(result);
        }
        function onCancel() { cleanup(false); }
        function onOk() { cleanup(true); }
        function onKey(e) {
            if (e.key === 'Escape') cleanup(false);
            if (e.key === 'Enter') cleanup(true);
        }

        btnCancel.addEventListener('click', onCancel);
        btnOk.addEventListener('click', onOk);
        document.addEventListener('keydown', onKey);
        btnCancel.focus();
    });
}

async function permanentDeleteFromTrash(caseId) {
    if (!(await showConfirm('确定要彻底删除此案件？此操作不可恢复。'))) return;
    try {
        const data = await API.permanentDeleteTrash(caseId);
        if (data.error) { showToast(data.error); return; }
        showToast('已彻底删除');
        state.trash = state.trash.filter(item => item.case_id !== caseId);
        renderTrashList();
    } catch (e) {
        showToast('彻底删除失败');
    }
}

async function emptyTrash() {
    if (!state.trash || !state.trash.length) { showToast('废纸篓已为空'); return; }
    if (!(await showConfirm(`确定清空废纸篓（共 ${state.trash.length} 个案件）？此操作不可恢复。`))) return;
    try {
        const data = await API.emptyTrash();
        if (data.error) { showToast(data.error); return; }
        showToast(`已清空 ${data.deleted} 个案件`);
        state.trash = [];
        renderTrashList();
    } catch (e) {
        showToast('清空失败');
    }
}

async function loadTrash() {
    try {
        const data = await API.getTrash();
        state.trash = data.trash || [];
    } catch (e) {
        state.trash = [];
    }
    renderTrashList();
}

function showNewCaseWizard() {
    populateNewCaseSettings();
    showEntryCover('new');
    dom.newCaseName.focus();
}

function showOldCaseChooser() {
    dom.entryTrashPanel.classList.add('hidden');
    renderEntryCaseList();
    showEntryCover('old');
    loadTrash();
}

function populateNewCaseSettings() {
    const settings = state.aiSettings || {};
    const strong = settings.strong || {};
    const cheap = settings.cheap || {};
    const mineru = settings.mineru || {};
    dom.newStrongBaseUrl.value = strong.base_url || '';
    dom.newStrongModel.value = strong.model || '';
    dom.newStrongApiKey.value = '';
    dom.newStrongApiKey.placeholder = strong.has_api_key ? '已保存，留空不修改' : '留空表示不配置';
    dom.newCheapBaseUrl.value = cheap.base_url || '';
    dom.newCheapModel.value = cheap.model || '';
    dom.newCheapApiKey.value = '';
    dom.newCheapApiKey.placeholder = cheap.has_api_key ? '已保存，留空不修改' : '留空表示不配置';
    dom.newMineruApiToken.value = '';
    dom.newMineruApiToken.placeholder = mineru.has_api_token ? '已保存，留空不修改' : '必须配置 MinerU Token';
    const hasReusableConfig = Boolean(
        strong.has_api_key && strong.base_url && strong.model &&
        cheap.has_api_key && cheap.base_url && cheap.model &&
        mineru.has_api_token
    );
    dom.newCaseUseExistingConfig.checked = hasReusableConfig;
    toggleNewCaseConfigFields();
    state.partyCandidates = [];
    renderNewClientCandidates([]);
}

function toggleNewCaseConfigFields() {
    const skip = dom.newCaseUseExistingConfig.checked;
    dom.newCaseConfigFields.classList.toggle('is-disabled', skip);
    dom.newCaseConfigFields.querySelectorAll('input, select, textarea').forEach(item => {
        item.disabled = skip;
    });
}

async function loadNewClientCandidates(caseId, query = '') {
    if (!caseId || !dom.newClientCandidateList) return;
    try {
        const data = await API.getPartyCandidates(caseId, query);
        state.partyCandidates = data.candidates || [];
        renderNewClientCandidates(state.partyCandidates);
    } catch (e) {
        state.partyCandidates = [];
        renderNewClientCandidates([]);
    }
}

function renderNewClientCandidates(candidates) {
    if (!dom.newClientCandidates || !dom.newClientCandidateList) return;
    const items = (candidates || []).slice(0, 10);
    dom.newClientCandidates.innerHTML = items.map(item => `
        <option value="${escapeAttr(item.name || '')}"></option>
    `).join('');
    if (!items.length) {
        dom.newClientCandidateList.innerHTML = '';
        return;
    }
    dom.newClientCandidateList.innerHTML = items.map(item => `
        <button type="button" class="client-candidate-chip" data-client-name="${escapeAttr(item.name || '')}">
            <span>${escapeHtml(item.name || '')}</span>
            <small>${escapeHtml((item.sources || []).join('、'))}</small>
        </button>
    `).join('');
}

async function loadCase(caseId) {
    state.currentCase = caseId;
    state.isSearchMode = false;
    state.searchKeywords = [];
    state.summaries = {};
    state.personSummaries = {};
    state.indictment = null;
    state.graph = null;
    state.partyContext = null;
    state.selectedParties = [];
    state.graphragStatus = null;
    state.graphragRetrieval = null;
    state.chatMessages = [];
    dom.searchStats.classList.add('hidden');
    dom.searchInput.value = '';
    if (dom.graphragQuery) dom.graphragQuery.value = '';

    await loadPartyContext(caseId);

    // 加载筛选条件
    const filters = await API.getFilters(caseId);
    populateSelect(dom.filterName, filters.names, '全部');
    populateSelect(dom.filterType, filters.types, '全部');
    populateSelect(dom.filterDate, filters.dates, '全部');

    // 加载笔录列表
    await loadRecords();

    // 如果当前不在笔录列表视图，刷新当前视图
    if (state.currentView !== 'records') {
        await refreshCurrentView();
    }
}

async function loadPartyContext(caseId) {
    try {
        const data = await API.getPartyContext(caseId);
        state.partyContext = data;
    } catch (e) {
        state.partyContext = {
            entrusted_parties: [],
            related_people: [],
            focus_people: [],
            indictment_summary: '',
            has_indictment: false,
        };
    }
    renderPartyContext();
    if ((state.partyContext.entrusted_parties || []).length === 0) {
        openCaseSetup();
    } else {
        closeCaseSetup();
    }
}

function populateSelect(select, options, defaultLabel) {
    select.innerHTML = `<option value="">${defaultLabel}</option>` +
        options.map(o => `<option value="${o}">${o}</option>`).join('');
}

async function loadRecords() {
    const params = { case: state.currentCase };
    const name = dom.filterName.value;
    const type = dom.filterType.value;
    const date = dom.filterDate.value;

    if (name) params.name = name;
    if (type) params.type = type;
    if (date) params.date = date;

    const data = await API.getRecords(params);
    state.records = data.records;
    state.isSearchMode = false;

    // 同时加载摘要数据
    try {
        const summaryData = await API.getSummaries(state.currentCase);
        state.summaries = summaryData.summaries || {};
    } catch (e) {
        state.summaries = {};
    }

    dom.recordCount.textContent = `${data.total}份`;
    dom.statusBar.textContent = `共 ${data.total} 份笔录`;
    renderRecords(data.records);
}

// 联动筛选：更新笔录列表 + 联动更新各下拉框的可选值
async function applyFilters() {
    const params = { case: state.currentCase };
    const name = dom.filterName.value;
    const type = dom.filterType.value;
    const date = dom.filterDate.value;

    if (name) params.name = name;
    if (type) params.type = type;
    if (date) params.date = date;

    // 并行请求笔录列表和联动筛选条件
    const [recordsData, filtersData] = await Promise.all([
        API.getRecords(params),
        API.getFilters(state.currentCase, { name, type, date }),
    ]);

    state.records = recordsData.records;
    state.isSearchMode = false;

    // 加载摘要
    try {
        const summaryData = await API.getSummaries(state.currentCase);
        state.summaries = summaryData.summaries || {};
    } catch (e) {
        state.summaries = {};
    }

    // 联动更新下拉框：保留当前有效值，自动清除已失效的值
    updateSelectKeepValue(dom.filterName, filtersData.names, name);
    updateSelectKeepValue(dom.filterType, filtersData.types, type);
    updateSelectKeepValue(dom.filterDate, filtersData.dates, date);

    dom.recordCount.textContent = `${recordsData.total}份`;
    dom.statusBar.textContent = `共 ${recordsData.total} 份笔录`;
    renderRecords(recordsData.records);
}

function updateSelectKeepValue(select, options, currentValue) {
    const keepValue = options.includes(currentValue) ? currentValue : '';
    select.innerHTML = `<option value="">全部</option>` +
        options.map(o => `<option value="${o}" ${o === keepValue ? 'selected' : ''}>${o}</option>`).join('');
}

function renderRecords(records) {
    if (records.length === 0) {
        dom.recordList.innerHTML = '<div class="record-card" style="text-align:center;color:#999;">未找到匹配的笔录</div>';
        return;
    }

    dom.recordList.innerHTML = records.map(r => {
        const typeClass = r.笔录类型 === '询问笔录' ? '询问' : '';
        const pageInfo = r.印刷页码 ? `P${r.印刷页码}` : '页码待补';
        const ciShu = r.次数 ? ` · ${r.次数}` : '';

        // 匹配页码
        let matchPageHtml = '';
        if (r.匹配页码) {
            matchPageHtml = `<div class="match-page">匹配位置：${escapeHtml(r.匹配页码)}</div>`;
        }

        // 匹配度
        let scoreHtml = '';
        if (state.isSearchMode && r.匹配分数) {
            scoreHtml = `<span class="score-badge">匹配度 ${r.匹配分数}</span>`;
        }

        // 片段（优先AI摘要，其次原始摘要）
        let snippetHtml = '';
        const aiSummary = state.summaries[r.id];
        if (aiSummary && aiSummary.content) {
            snippetHtml = `
                <div class="snippet ai-summary">
                    <div class="ai-summary-badge">AI 摘要</div>
                    ${highlightKeywords(aiSummary.content.slice(0, 200))}${aiSummary.content.length > 200 ? '...' : ''}
                </div>
            `;
        } else if (r.匹配片段) {
            snippetHtml = `<div class="snippet">${highlightKeywords(r.匹配片段)}</div>`;
        } else if (r.内容摘要) {
            snippetHtml = `<div class="snippet">${highlightKeywords(r.内容摘要.slice(0, 150))}...</div>`;
        }

        return `
            <div class="record-card" data-id="${r.id}">
                <div class="card-header">
                    <span class="person-name">${escapeHtml(r.姓名)}</span>
                    <span class="record-type ${typeClass}">${escapeHtml(r.笔录类型)}${ciShu}${scoreHtml}</span>
                </div>
                <div class="meta">
                    <span>${escapeHtml(r.日期)}</span>
                    <span>${pageInfo}</span>
                    ${r.匹配来源 ? `<span>匹配: ${r.匹配来源}</span>` : ''}
                </div>
                ${matchPageHtml}
                <div class="citation">
                    <span>${escapeHtml(r.引用格式)}</span>
                    <button class="copy-btn" data-citation="${escapeAttr(r.引用格式)}">复制</button>
                </div>
                ${snippetHtml}
            </div>
        `;
    }).join('');
}

async function showRecord(recordId) {
    const data = await API.getRecord(state.currentCase, recordId);
    if (data.error) {
        alert(data.error);
        return;
    }

    dom.modalTitle.textContent = `${data.姓名} - ${data.笔录类型}${data.次数 ? ' ' + data.次数 : ''}`;
    dom.modalCitationText.textContent = data.引用格式;
    dom.btnCopy.dataset.citation = data.引用格式;

    // AI摘要
    const aiSummary = state.summaries[recordId];
    if (aiSummary && aiSummary.content) {
        dom.modalAiSummaryText.textContent = aiSummary.content;
        dom.modalAiSummary.classList.remove('hidden');
    } else {
        dom.modalAiSummary.classList.add('hidden');
    }

    // 渲染原文，清洗并保留基本格式
    let content = data.原文内容 || '无内容';
    // 清洗HTML表格为可读格式
    content = content.replace(/<table>/g, '\n');
    content = content.replace(/<\/table>/g, '\n');
    content = content.replace(/<tr>/g, '');
    content = content.replace(/<\/tr>/g, '\n');
    content = content.replace(/<td[^>]*>/g, '');
    content = content.replace(/<\/td>/g, ' ');
    content = content.replace(/<[^>]+>/g, '');
    // 清洗markdown图片引用
    content = content.replace(/!\[.*?\]\(.*?\)/g, '');
    // 清洗页码标记
    content = content.replace(/第\s*\d+\s*页\s*共\s*\d+\s*页/g, '');
    // 清洗标题标记（保留文字）
    content = content.replace(/^#{1,3}\s+/gm, '');
    // 压缩连续空行
    content = content.replace(/\n{3,}/g, '\n\n');
    dom.modalContent.textContent = content.trim();

    dom.modal.classList.remove('hidden');
}

function copyToClipboard(text, btnEl) {
    const doCopy = () => {
        navigator.clipboard.writeText(text).then(() => {
            showToast('已复制到剪贴板');
            if (btnEl) flashCopied(btnEl);
        }).catch(() => {
            const ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            showToast('已复制到剪贴板');
            if (btnEl) flashCopied(btnEl);
        });
    };
    doCopy();
}

function flashCopied(btnEl) {
    const original = btnEl.textContent;
    btnEl.textContent = '已复制';
    btnEl.classList.add('copied');
    setTimeout(() => {
        btnEl.textContent = original;
        btnEl.classList.remove('copied');
    }, 1500);
}

function showToast(msg) {
    const toast = document.createElement('div');
    toast.className = 'copy-toast';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2000);
}

function highlightKeywords(text) {
    if (!text) return '';
    const escaped = escapeHtml(text);
    if (state.searchKeywords.length === 0) return escaped;

    const pattern = state.searchKeywords
        .map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
        .join('|');
    if (!pattern) return escaped;

    const re = new RegExp(`(${pattern})`, 'gi');
    return escaped.replace(re, '<span class="match-highlight">$1</span>');
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderMarkdown(text) {
    if (!text) return '';
    // Split into blocks (paragraphs, tables, code blocks)
    const blocks = text.split(/\n{2,}/);
    return blocks.map(block => {
        const trimmed = block.trim();
        if (!trimmed) return '';
        // Code block
        if (trimmed.startsWith('```')) {
            const lines = trimmed.split('\n');
            const lang = lines[0].slice(3).trim();
            const code = lines.slice(1, -1).join('\n');
            return `<pre class="md-code${lang ? ' md-code--' + escapeHtml(lang) : ''}"><code>${escapeHtml(code)}</code></pre>`;
        }
        // Table: lines all start/contain |
        const lines = trimmed.split('\n');
        if (lines.length >= 2 && lines.every(l => l.trim().startsWith('|'))) {
            return _renderTable(lines);
        }
        // Inline formatting for regular paragraphs
        return `<p>${_renderInline(trimmed)}</p>`;
    }).join('');
}

function _renderTable(lines) {
    // Skip separator line (|---|---|)
    const rows = lines.filter(l => !/^\|[\s\-:|]+\|$/.test(l.trim()));
    if (rows.length === 0) return '';
    const headerCells = _parseTableRow(rows[0]);
    const thead = `<thead><tr>${headerCells.map(c => `<th>${_renderInline(c)}</th>`).join('')}</tr></thead>`;
    const tbody = rows.length > 1
        ? `<tbody>${rows.slice(1).map(row => {
            const cells = _parseTableRow(row);
            return `<tr>${cells.map(c => `<td>${_renderInline(c)}</td>`).join('')}</tr>`;
        }).join('')}</tbody>`
        : '';
    return `<table class="md-table">${thead}${tbody}</table>`;
}

function _parseTableRow(line) {
    return line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
}

function _renderInline(text) {
    let html = escapeHtml(text);
    // Bold: **text**
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Inline code: `text`
    html = html.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');
    // Headers in single-line blocks
    html = html.replace(/^### (.+)$/gm, '<h3 class="md-h3">$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2 class="md-h2">$1</h2>');
    // Horizontal rule
    html = html.replace(/^---$/gm, '<hr class="md-hr">');
    return html;
}

function escapeAttr(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function formatDisplayValue(value) {
    if (Array.isArray(value)) {
        return value.join('、');
    }
    if (value && typeof value === 'object') {
        return Object.entries(value)
            .map(([key, item]) => `${key}：${item}`)
            .join('；');
    }
    return value || '';
}

function renderNameTags(container, items, emptyText) {
    if (!items || items.length === 0) {
        container.innerHTML = `<span class="party-empty">${escapeHtml(emptyText)}</span>`;
        return;
    }

    container.innerHTML = items.map(item => `
        <span class="party-tag">${escapeHtml(item)}</span>
    `).join('');
}

function renderPartyContext() {
    const context = state.partyContext || {};
    const focusPeople = context.focus_people || [];
    const entrusted = context.entrusted_parties || [];
    const related = context.related_people || [];
    const summary = context.indictment_summary || '';

    if (focusPeople.length === 0) {
        dom.partyContextOptions.innerHTML = '<div class="party-empty">当前案件还没有可供选择的人物。</div>';
    } else {
        dom.partyContextOptions.innerHTML = focusPeople.map(name => `
            <label class="party-choice">
                <input type="checkbox" value="${escapeAttr(name)}" ${entrusted.includes(name) ? 'checked' : ''}>
                <span>${escapeHtml(name)}</span>
            </label>
        `).join('');
    }

    renderNameTags(dom.partyContextCurrent, entrusted, '尚未确认委托人');
    renderNameTags(dom.partyContextRelated, related, '尚未提取涉案核心人物');
    dom.partyContextSummary.textContent = summary || '当前还没有起诉书主线摘要。';
    renderCaseContextBar();
}

function renderCaseContextBar() {
    const context = state.partyContext || {};
    const entrusted = context.entrusted_parties || [];
    const related = context.related_people || [];
    dom.caseContextClient.textContent = entrusted.length > 0 ? entrusted.join('、') : '未确认';
    dom.caseContextStatus.textContent = related.length > 0
        ? `涉案核心人物 ${related.length} 人`
        : '尚未提取涉案核心人物';
}

function openCaseSetup() {
    dom.workflowPanel.classList.remove('hidden');
}

function closeCaseSetup() {
    dom.workflowPanel.classList.add('hidden');
}

function getSelectedEntrustedParties() {
    return Array.from(dom.partyContextOptions.querySelectorAll('input[type="checkbox"]'))
        .filter(input => input.checked)
        .map(input => input.value);
}

async function savePartyContext() {
    const entrustedParties = getSelectedEntrustedParties();
    if (entrustedParties.length === 0) {
        showToast('请先勾选至少一位委托人');
        return;
    }

    const currentRelated = (state.partyContext && state.partyContext.related_people) || [];
    dom.btnSavePartyContext.disabled = true;
    dom.btnSavePartyContext.textContent = '保存中...';

    try {
        const data = await API.savePartyContext(state.currentCase, entrustedParties, currentRelated);
        if (data.error) {
            showToast(data.error);
            return;
        }

        state.partyContext = data;
        state.selectedParties = [...(data.entrusted_parties || data.focus_people || [])];
        renderPartyContext();
        closeCaseSetup();

        if (state.currentView === 'graph' && state.graph && state.graph.has_graph) {
            initPartyFilter();
            renderGraph();
        }

        showToast('委托人设置已保存');
    } catch (err) {
        showToast('保存失败，请重试');
        console.error(err);
    } finally {
        dom.btnSavePartyContext.disabled = false;
        dom.btnSavePartyContext.textContent = '保存设置';
    }
}

// ============================
// 视图切换
// ============================

function switchView(viewName) {
    state.currentView = viewName;

    // 更新tab样式
    dom.viewTabs.querySelectorAll('.view-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.view === viewName);
    });

    // 显示/隐藏视图容器
    dom.viewRecords.classList.toggle('hidden', viewName !== 'records');
    dom.viewPersons.classList.toggle('hidden', viewName !== 'persons');
    dom.viewGraph.classList.toggle('hidden', viewName !== 'graph');
    dom.viewIndictment.classList.toggle('hidden', viewName !== 'indictment');
    dom.viewAi.classList.toggle('hidden', viewName !== 'ai');
    dom.viewEvidence.classList.toggle('hidden', viewName !== 'evidence');

    // 搜索栏只在笔录列表显示
    dom.searchHero.classList.toggle('hidden', viewName !== 'records');

    // 按需加载数据
    refreshCurrentView();
}

async function refreshCurrentView() {
    if (!state.currentCase) return;

    switch (state.currentView) {
        case 'records':
            await loadRecords();
            break;
        case 'persons':
            await loadPersonsView();
            break;
        case 'graph':
            await loadGraphView();
            break;
        case 'indictment':
            await loadIndictmentView();
            break;
        case 'ai':
            await loadAIView();
            break;
        case 'evidence':
            await loadEvidenceView();
            break;
    }
}

// ============================
// 证据材料视图
// ============================
let evidenceState = {
    directory: [],
    selected: new Set(),
    parseJobId: null,
};

async function loadEvidenceView() {
    const bar = document.getElementById('evidence-status-bar');
    bar.textContent = '加载中...';
    try {
        const data = await fetch(`/api/evidence-directory?case=${encodeURIComponent(state.currentCase)}`).then(r => r.json());
        if (data.error) {
            bar.textContent = data.error;
            return;
        }
        evidenceState.directory = data.directory || [];
        bar.textContent = evidenceState.directory.length
            ? `共 ${evidenceState.directory.length} 条，页码偏移: ${data.page_offset || 0}`
            : data.message || '暂无证据目录';
        renderEvidenceDirectory();
    } catch (e) {
        bar.textContent = '加载失败';
    }
}

function renderEvidenceDirectory() {
    const groups = document.getElementById('evidence-groups');
    const filter = document.getElementById('evidence-type-filter');
    const dir = evidenceState.directory;

    if (!dir.length) {
        groups.innerHTML = '<div class="evidence-empty">暂无证据目录数据。<br>请先完成自动建库，系统将自动解析证据卷目录。</div>';
        filter.innerHTML = '<option value="">全部类型</option>';
        return;
    }

    // Group by type
    const byType = {};
    for (const d of dir) {
        const t = d['证据类型'] || '其他';
        if (!byType[t]) byType[t] = [];
        byType[t].push(d);
    }

    // Update filter dropdown
    const types = Object.keys(byType).sort();
    filter.innerHTML = '<option value="">全部类型</option>' +
        types.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)} (${byType[t].length})</option>`).join('');

    const filterVal = filter.value;

    let html = '';
    for (const [type, items] of Object.entries(byType)) {
        if (filterVal && type !== filterVal) continue;
        const parsedCount = items.filter(d => d['解析状态'] === 'completed').length;
        html += '<div class="evidence-group" data-expanded="false">';
        html += `<div class="evidence-group-header" onclick="toggleEvidenceGroup(this)">
            <span class="evidence-group-caret">▶</span>
            <span class="evidence-group-title">${escapeHtml(type)}</span>
            <span class="evidence-group-count">${items.length}条${parsedCount ? `<span class="count-parsed"> / ${parsedCount}已解析</span>` : ''}</span>
        </div>`;
        html += '<div class="evidence-group-body">';

        // — group-level select checkbox —
        html += '<div class="evidence-group-select-row">';
        html += `<label><input type="checkbox" onchange="toggleEvidenceGroupSelect(this)" data-type="${escapeHtml(type)}"> 全选本组</label>`;
        html += '</div>';

        // — item rows —
        for (const d of items) {
            const sel = evidenceState.selected.has(d.index);
            const parsed = d['解析状态'] === 'completed';
            html += `<div class="evidence-item-row" onclick="toggleEvidenceItemFromClick(this, ${d.index})">`;
            html += `<input type="checkbox" ${sel ? 'checked' : ''} onclick="event.stopPropagation(); toggleEvidenceItem(${d.index}, this.checked)">`;
            html += `<span class="evidence-item-idx">${d.index}</span>`;
            html += `<span class="evidence-item-name">${escapeHtml(d['名称'] || '')}${parsed ? '<span class="evidence-status-tag parsed">已解析</span>' : ''}</span>`;
            html += `<span class="evidence-item-pages">P${d['证据卷页码'][0]}-${d['证据卷页码'][1]}</span>`;
            html += `<span class="evidence-item-date">${escapeHtml(d['日期'] || '')}</span>`;
            html += `<span class="evidence-item-count">${d['页数']}p</span>`;
            html += '</div>';
        }

        html += '</div></div>';
    }

    groups.innerHTML = html;
    updateEvidenceSelectedCount();
}

function toggleEvidenceGroup(header) {
    const group = header.parentElement; // .evidence-group
    const isExpanded = group.getAttribute('data-expanded') === 'true';

    // Accordion: close all other groups first
    if (!isExpanded) {
        const allGroups = document.querySelectorAll('.evidence-group[data-expanded="true"]');
        for (const g of allGroups) {
            g.setAttribute('data-expanded', 'false');
        }
    }

    // Toggle this group
    group.setAttribute('data-expanded', isExpanded ? 'false' : 'true');
}

function toggleEvidenceItemFromClick(row, index) {
    const cb = row.querySelector('input[type="checkbox"]');
    if (cb) {
        cb.checked = !cb.checked;
        toggleEvidenceItem(index, cb.checked);
    }
}

function toggleEvidenceItem(index, checked) {
    if (checked) {
        evidenceState.selected.add(index);
    } else {
        evidenceState.selected.delete(index);
    }
    updateEvidenceSelectedCount();
}

function toggleEvidenceGroupSelect(checkbox) {
    const type = checkbox.dataset.type;
    const items = evidenceState.directory.filter(d => d['证据类型'] === type && d['解析状态'] !== 'completed');
    for (const d of items) {
        if (checkbox.checked) {
            evidenceState.selected.add(d.index);
        } else {
            evidenceState.selected.delete(d.index);
        }
    }
    renderEvidenceDirectory();
}

function updateEvidenceSelectedCount() {
    document.getElementById('evidence-selected-count').textContent =
        `已选 ${evidenceState.selected.size} 条`;
}

async function parseSelectedEvidence() {
    if (!evidenceState.selected.size) {
        showToast('请先勾选要解析的证据条目');
        return;
    }
    const entries = Array.from(evidenceState.selected);
    const bar = document.getElementById('evidence-status-bar');
    const btn = document.getElementById('btn-evidence-parse');
    btn.disabled = true;
    btn.textContent = '提交中...';
    bar.textContent = `正在提交解析请求（${entries.length} 条）...`;
    try {
        const res = await fetch('/api/evidence/parse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case: state.currentCase, entries }),
        });
        const data = await res.json();
        if (data.error) {
            showToast(data.error);
            bar.textContent = data.error;
            return;
        }
        evidenceState.parseJobId = data.job ? data.job.id : '';
        evidenceState.selected.clear();
        bar.textContent = `解析任务已启动，正在后台处理...`;
        showToast(`已提交 ${entries.length} 条证据的解析任务`);
        pollEvidenceParseJob();
    } catch (e) {
        showToast('提交失败');
        bar.textContent = '提交失败';
    } finally {
        btn.disabled = false;
        btn.textContent = '解析选中证据';
    }
}

async function pollEvidenceParseJob() {
    if (!evidenceState.parseJobId) return;
    try {
        const res = await fetch(`/api/jobs/${evidenceState.parseJobId}`);
        const data = await res.json();
        const job = data.job || {};
        const bar = document.getElementById('evidence-status-bar');
        bar.textContent = `解析进度: ${job.message || job.status}`;
        if (job.status === 'completed') {
            bar.textContent = `解析完成: ${job.message}`;
            evidenceState.parseJobId = null;
            await loadEvidenceView(); // Reload to show parsed tags
            const rebuild = await showConfirm('证据解析已完成。是否重建 GraphRAG 索引？\n\n新解析的证据内容需要重建索引后才能被 GraphRAG 检索到。');
            if (rebuild) {
                bar.textContent = '正在重建 GraphRAG 索引...';
                await rebuildGraphRAGIndex();
                bar.textContent = '解析完成，GraphRAG 索引已重建';
            }
        } else if (job.status === 'failed') {
            bar.textContent = `解析失败: ${job.message}`;
            evidenceState.parseJobId = null;
        } else {
            setTimeout(pollEvidenceParseJob, 3000);
        }
    } catch (e) {
        setTimeout(pollEvidenceParseJob, 5000);
    }
}

// ============================
// 人物视图
// ============================

async function loadPersonsView() {
    if (Object.keys(state.personSummaries).length === 0) {
        try {
            const data = await API.getPersonSummaries(state.currentCase);
            state.personSummaries = data.person_summaries || {};
        } catch (e) {
            state.personSummaries = {};
        }
    }

    const persons = Object.entries(state.personSummaries);
    // 按姓名拼音排序
    persons.sort((a, b) => a[0].localeCompare(b[0], 'zh-CN'));

    dom.personsStatusBar.textContent = `共 ${persons.length} 人`;

    if (persons.length === 0) {
        dom.personList.innerHTML = '<div style="text-align:center;color:#999;padding:40px;">暂无人物摘要数据</div>';
        return;
    }

    dom.personList.innerHTML = persons.map(([name, info]) => {
        const summary = info.综合摘要 || info.content || '暂无摘要';
        const count = info.笔录数量 || info.record_count || 0;
        const role = info.角色定位 || '';
        const attitude = info.认罪态度 || '';
        const roleBadge = role ? `<span class="person-role-badge">${escapeHtml(role)}</span>` : '';
        const attitudeBadge = attitude ? `<span class="person-attitude-badge">${escapeHtml(attitude)}</span>` : '';
        return `
            <div class="person-card" data-name="${escapeAttr(name)}">
                <div class="person-card-header">
                    <span class="person-card-name">${escapeHtml(name)}</span>
                    ${roleBadge}
                    <span class="person-card-count">${count} 份笔录</span>
                    ${attitudeBadge}
                </div>
                <div class="person-card-summary">${escapeHtml(summary)}</div>
                <div class="person-card-expand-hint"></div>
            </div>
        `;
    }).join('');
}

function togglePersonCard(card) {
    card.classList.toggle('expanded');
}

// ============================
// 案情图谱
// ============================

async function loadGraphView() {
    if (!state.graph) {
        try {
            const data = await API.getGraph(state.currentCase);
            state.graph = data;
        } catch (e) {
            state.graph = { has_graph: false, nodes: [], edges: [], parties: [] };
        }
    }

    if (!state.graph.has_graph || state.graph.nodes.length === 0) {
        dom.graphEmpty.classList.remove('hidden');
        dom.graphSidebar.classList.add('hidden');
        dom.btnExportDrawio.classList.add('hidden');
        // 清除之前的svg
        const oldSvg = dom.graphContainer.querySelector('.graph-svg');
        if (oldSvg) oldSvg.remove();
        return;
    }

    dom.graphEmpty.classList.add('hidden');
    dom.graphSidebar.classList.add('hidden');
    dom.btnExportDrawio.classList.remove('hidden');
    dom.btnExportDrawio.href = API.getDrawioUrl(state.currentCase);
    state.selectedParties = getGraphCenterLabels();

    // 渲染图谱
    renderGraph();
}

function initPartyFilter() {
    const context = state.partyContext || {};
    const parties = state.graph.parties || context.focus_people || [];
    const entrusted = context.entrusted_parties || [];

    if (state.selectedParties.length === 0 && parties.length > 0) {
        state.selectedParties = entrusted.length > 0 ? [...entrusted] : [...parties];
    }

    dom.partyList.innerHTML = parties.map(p => `
        <label class="party-item">
            <input type="checkbox" value="${escapeAttr(p)}" ${state.selectedParties.includes(p) ? 'checked' : ''}>
            <span>${escapeHtml(p)}</span>
        </label>
    `).join('');
}

function updatePartyFilter() {
    const checkboxes = dom.partyList.querySelectorAll('input[type="checkbox"]');
    state.selectedParties = Array.from(checkboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.value);
    renderGraph();
}

function selectAllParties() {
    const context = state.partyContext || {};
    const parties = state.graph.parties || context.focus_people || [];
    state.selectedParties = [...parties];
    const checkboxes = dom.partyList.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(cb => cb.checked = true);
    renderGraph();
}

function getNodeColor(type) {
    const colors = {
        person: '#2563eb',
        organization: '#059669',
        account: '#d97706',
        other: '#64748b',
    };
    return colors[type] || colors.other;
}

function getNodeRadius(node) {
    if (isGraphCenterLabel(node.label)) return 28;
    if (node.importance === 'primary') return 22;
    if (node.importance === 'secondary') return 16;
    return 12;
}

function renderGraph() {
    if (state.graphMode === 'mindmap') {
        renderMindMap();
        return;
    }
    renderNetworkGraph();
}

function clearGraphCanvas() {
    const container = dom.graphContainer;
    const oldSvg = container.querySelector('.graph-svg');
    if (oldSvg) oldSvg.remove();
    const oldTooltip = container.querySelector('.graph-tooltip');
    if (oldTooltip) oldTooltip.remove();
}

function getVisibleGraphData() {
    if (!state.graph || !state.graph.nodes) return { nodes: [], edges: [] };

    const centerLabels = new Set(getGraphCenterLabels());
    const allPersonNodes = state.graph.nodes.filter(isDisplayPersonNode);
    const allPersonNodeIds = new Set(allPersonNodes.map(n => n.id));
    const allPersonEdges = state.graph.edges.filter(e => {
        const s = getNodeId(e.source);
        const t = getNodeId(e.target);
        return allPersonNodeIds.has(s) && allPersonNodeIds.has(t);
    });

    if (centerLabels.size === 0) {
        return { nodes: allPersonNodes, edges: allPersonEdges };
    }

    const centerNodeIds = new Set(
        allPersonNodes
            .filter(n => centerLabels.has(n.label))
            .map(n => n.id)
    );
    if (centerNodeIds.size === 0) {
        return { nodes: allPersonNodes, edges: allPersonEdges };
    }

    const adjacency = new Map();
    allPersonNodes.forEach(node => adjacency.set(node.id, new Set()));
    allPersonEdges.forEach(edge => {
        const source = getNodeId(edge.source);
        const target = getNodeId(edge.target);
        adjacency.get(source)?.add(target);
        adjacency.get(target)?.add(source);
    });

    const visibleNodeIds = new Set(centerNodeIds);
    const queue = Array.from(centerNodeIds);
    while (queue.length > 0) {
        const current = queue.shift();
        (adjacency.get(current) || []).forEach(next => {
            if (!visibleNodeIds.has(next)) {
                visibleNodeIds.add(next);
                queue.push(next);
            }
        });
    }

    const nodes = allPersonNodes.filter(n => visibleNodeIds.has(n.id));
    const edges = allPersonEdges.filter(e => {
        const s = getNodeId(e.source);
        const t = getNodeId(e.target);
        return visibleNodeIds.has(s) && visibleNodeIds.has(t);
    });

    return { nodes, edges };
}

function getGraphCenterLabels() {
    const graphCenters = (state.graph && (state.graph.center_parties || state.graph.parties)) || [];
    const contextCenters = (state.partyContext && state.partyContext.entrusted_parties) || [];
    const centers = graphCenters.length > 0 ? graphCenters : contextCenters;
    return Array.from(new Set(centers.filter(Boolean)));
}

function isGraphCenterLabel(label) {
    return getGraphCenterLabels().includes(label);
}

function isDisplayPersonNode(node) {
    if (!node || node.type !== 'person') return false;
    const label = String(node.label || '');
    if (!label) return false;
    if (Array.isArray(node.members) && node.members.length > 0) return false;
    return !/(团伙|买家|客户|对象|群体|车辆|货车|轿车|账户|仓库|山庄|酒店|工地)/.test(label);
}

function getNodeId(value) {
    return typeof value === 'object' ? value.id : value;
}

function getGraphDistances(nodes, edges, centerIds) {
    const adjacency = new Map();
    nodes.forEach(node => adjacency.set(node.id, new Set()));
    edges.forEach(edge => {
        const source = getNodeId(edge.source);
        const target = getNodeId(edge.target);
        adjacency.get(source)?.add(target);
        adjacency.get(target)?.add(source);
    });

    const distances = new Map();
    const queue = Array.from(centerIds);
    queue.forEach(id => distances.set(id, 0));

    while (queue.length > 0) {
        const current = queue.shift();
        const nextDistance = (distances.get(current) || 0) + 1;
        (adjacency.get(current) || []).forEach(next => {
            if (!distances.has(next)) {
                distances.set(next, nextDistance);
                queue.push(next);
            }
        });
    }

    return distances;
}

function assignMindMapSides(directNodes, indirectNodes, edges, centerIds) {
    const sideMap = new Map();
    directNodes.forEach(node => {
        const centerEdgeLabels = edges
            .filter(edge => {
                const source = getNodeId(edge.source);
                const target = getNodeId(edge.target);
                return (centerIds.has(source) && target === node.id) || (centerIds.has(target) && source === node.id);
            })
            .map(edge => edge.label || '')
            .join(' ');
        const shouldPlaceRight = /接驳|押运|转运|驾驶|等待|参与|被抓获|辅助/.test(centerEdgeLabels);
        sideMap.set(node.id, shouldPlaceRight ? 'right' : 'left');
    });

    const pending = new Set(indirectNodes.map(node => node.id));
    let changed = true;
    while (changed && pending.size > 0) {
        changed = false;
        for (const nodeId of Array.from(pending)) {
            const linkedSides = edges
                .filter(edge => getNodeId(edge.source) === nodeId || getNodeId(edge.target) === nodeId)
                .map(edge => {
                    const otherId = getNodeId(edge.source) === nodeId ? getNodeId(edge.target) : getNodeId(edge.source);
                    return sideMap.get(otherId);
                })
                .filter(Boolean);
            if (linkedSides.length > 0) {
                sideMap.set(nodeId, linkedSides[0]);
                pending.delete(nodeId);
                changed = true;
            }
        }
    }

    Array.from(pending).forEach((nodeId, index) => {
        sideMap.set(nodeId, index % 2 === 0 ? 'left' : 'right');
    });

    return sideMap;
}

function safeGraphText(text) {
    if (!text) return '';
    return String(text)
        .replaceAll('首要分子', '组织作用')
        .replaceAll('主犯', '核心作用')
        .replaceAll('从犯', '辅助作用')
        .replaceAll('共犯', '共同参与');
}

function getFlowType(edge) {
    if (edge.flow) return edge.flow;
    const text = edge.label || '';
    if (/付款|收款|转账|资金|定金|打款|账户|支付/.test(text)) return '资金流';
    if (/采购|销售|运输|转运|接驳|发货|收货|仓库|货/.test(text)) return '货物流';
    if (/指派|安排|联系|介绍|通知|沟通|控制|管理/.test(text)) return '指挥联络';
    if (/证明|供述|辨认|证实|印证/.test(text)) return '证据关系';
    return '事实关系';
}

function renderMindMap() {
    clearGraphCanvas();

    const container = dom.graphContainer;
    const width = container.clientWidth;
    const height = container.clientHeight;
    const { nodes: visibleNodes, edges: visibleEdges } = getVisibleGraphData();

    if (visibleNodes.length === 0) {
        dom.graphEmpty.classList.remove('hidden');
        return;
    }
    dom.graphEmpty.classList.add('hidden');

    const centerLabels = new Set(getGraphCenterLabels());
    let centerNodes = visibleNodes.filter(n => centerLabels.has(n.label));
    if (centerNodes.length === 0) {
        centerNodes = visibleNodes.filter(n => n.importance === 'primary').slice(0, 1);
    }
    if (centerNodes.length === 0) {
        centerNodes = visibleNodes.slice(0, 1);
    }
    const centerIds = new Set(centerNodes.map(n => n.id));
    const distances = getGraphDistances(visibleNodes, visibleEdges, centerIds);
    const directNodes = visibleNodes
        .filter(n => !centerIds.has(n.id) && distances.get(n.id) === 1)
        .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
    const indirectNodes = visibleNodes
        .filter(n => !centerIds.has(n.id) && distances.get(n.id) !== 1)
        .sort((a, b) => (distances.get(a.id) || 9) - (distances.get(b.id) || 9) || a.label.localeCompare(b.label, 'zh-CN'));

    const sideMap = assignMindMapSides(directNodes, indirectNodes, visibleEdges, centerIds);
    const direct = {
        left: directNodes.filter(n => sideMap.get(n.id) !== 'right'),
        right: directNodes.filter(n => sideMap.get(n.id) === 'right'),
    };
    const indirect = {
        left: indirectNodes.filter(n => sideMap.get(n.id) !== 'right'),
        right: indirectNodes.filter(n => sideMap.get(n.id) === 'right'),
    };
    const maxColumnRows = Math.max(
        centerNodes.length,
        direct.left.length,
        direct.right.length,
        indirect.left.length,
        indirect.right.length,
        1
    );
    const canvasWidth = Math.max(width, 1500);
    const canvasHeight = Math.max(height, maxColumnRows * 118 + 200);
    const centerX = canvasWidth / 2 - 125;
    const positioned = new Map();

    const placeColumn = (items, x, boxW, boxH, gap) => {
        const startY = canvasHeight / 2 - ((items.length - 1) * gap + boxH) / 2;
        items.forEach((node, index) => {
            positioned.set(node.id, { ...node, x, y: startY + index * gap, w: boxW, h: boxH });
        });
    };

    placeColumn(indirect.left, centerX - 620, 220, 68, 108);
    placeColumn(direct.left, centerX - 330, 230, 72, 112);
    placeColumn(centerNodes, centerX, 250, 80, 122);
    placeColumn(direct.right, centerX + 350, 230, 72, 112);
    placeColumn(indirect.right, centerX + 640, 220, 68, 108);

    const svg = d3.select(container)
        .append('svg')
        .attr('class', 'graph-svg mindmap-svg')
        .attr('width', width)
        .attr('height', height)
        .attr('viewBox', `0 0 ${canvasWidth} ${canvasHeight}`);

    svg.append('defs')
        .append('marker')
        .attr('id', 'mindmap-arrow')
        .attr('viewBox', '0 0 10 10')
        .attr('refX', 9)
        .attr('refY', 5)
        .attr('markerWidth', 7)
        .attr('markerHeight', 7)
        .attr('orient', 'auto-start-reverse')
        .append('path')
        .attr('d', 'M 0 0 L 10 5 L 0 10 z')
        .attr('fill', '#333333');

    const g = svg.append('g');
    const zoom = d3.zoom()
        .scaleExtent([0.4, 2.5])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });
    svg.call(zoom);

    g.append('text')
        .attr('x', canvasWidth / 2)
        .attr('y', 56)
        .attr('text-anchor', 'middle')
        .attr('class', 'mindmap-title')
        .text(`${state.graph.case_name || '案情导图'}｜中心：${getGraphCenterLabels().join('、') || '未确认委托人'}`);

    const linkData = visibleEdges
        .map(edge => ({
            ...edge,
            sourceNode: positioned.get(typeof edge.source === 'object' ? edge.source.id : edge.source),
            targetNode: positioned.get(typeof edge.target === 'object' ? edge.target.id : edge.target),
        }))
        .filter(edge => edge.sourceNode && edge.targetNode);

    g.append('g')
        .attr('class', 'mindmap-links')
        .selectAll('path')
        .data(linkData)
        .enter()
        .append('path')
        .attr('class', d => {
            const classes = ['mindmap-link', `flow-${getFlowType(d)}`];
            if (d.style === 'dashed') classes.push('dashed');
            return classes.join(' ');
        })
        .attr('d', d => {
            return getMindMapPath(d);
        });

    g.append('g')
        .attr('class', 'mindmap-labels')
        .selectAll('text')
        .data(linkData.filter(d => d.label))
        .enter()
        .append('text')
        .attr('class', 'mindmap-edge-label')
        .attr('x', d => getMindMapLabelPoint(d).x)
        .attr('y', d => getMindMapLabelPoint(d).y)
        .attr('text-anchor', 'middle')
        .attr('class', d => `mindmap-edge-label flow-${getFlowType(d)}`)
        .text(d => safeGraphText(d.label));

    const nodeGroup = g.append('g')
        .attr('class', 'mindmap-nodes')
        .selectAll('g')
        .data(Array.from(positioned.values()))
        .enter()
        .append('g')
        .attr('transform', d => `translate(${d.x},${d.y})`)
        .attr('class', d => isGraphCenterLabel(d.label) || d.importance === 'primary' ? 'mindmap-node primary' : 'mindmap-node');

    nodeGroup.append('rect')
        .attr('width', d => d.w)
        .attr('height', d => d.h)
        .attr('rx', 6)
        .attr('ry', 6)
        .attr('class', d => `mindmap-box ${d.type || 'other'}`);

    nodeGroup.append('text')
        .attr('x', d => d.w / 2)
        .attr('y', 25)
        .attr('text-anchor', 'middle')
        .attr('class', 'mindmap-node-title')
        .text(d => safeGraphText(d.label));

    nodeGroup.append('text')
        .attr('x', d => d.w / 2)
        .attr('y', 46)
        .attr('text-anchor', 'middle')
        .attr('class', 'mindmap-node-subtitle')
        .text(d => safeGraphText(d.subtype || truncateText(d.description || '', 18)));
}

function getMindMapAnchors(edge) {
    const source = edge.sourceNode;
    const target = edge.targetNode;
    const sourceCenterX = source.x + source.w / 2;
    const targetCenterX = target.x + target.w / 2;
    const leftToRight = sourceCenterX <= targetCenterX;
    return {
        sx: leftToRight ? source.x + source.w : source.x,
        sy: source.y + source.h / 2,
        tx: leftToRight ? target.x : target.x + target.w,
        ty: target.y + target.h / 2,
        leftToRight,
    };
}

function getMindMapPath(edge) {
    const a = getMindMapAnchors(edge);
    const laneOffset = {
        '货物流': 0,
        '资金流': 18,
        '指挥联络': -18,
        '证据关系': 36,
        '事实关系': -36,
    }[getFlowType(edge)] || 0;
    const midX = (a.sx + a.tx) / 2 + laneOffset;
    return `M${a.sx},${a.sy} L${midX},${a.sy} L${midX},${a.ty} L${a.tx},${a.ty}`;
}

function getMindMapLabelPoint(edge) {
    const a = getMindMapAnchors(edge);
    const laneOffset = {
        '货物流': 0,
        '资金流': 18,
        '指挥联络': -18,
        '证据关系': 36,
        '事实关系': -36,
    }[getFlowType(edge)] || 0;
    const midX = (a.sx + a.tx) / 2 + laneOffset;
    const y = (a.sy + a.ty) / 2;
    return {
        x: midX,
        y: y - 10,
    };
}

function truncateText(text, maxLength) {
    if (!text) return '';
    return text.length > maxLength ? text.slice(0, maxLength).trim() + '...' : text;
}

function renderNetworkGraph() {
    const container = dom.graphContainer;
    const width = container.clientWidth;
    const height = container.clientHeight;

    clearGraphCanvas();

    const { nodes: visibleNodes, edges: visibleEdges } = getVisibleGraphData();

    if (visibleNodes.length === 0) {
        dom.graphEmpty.classList.remove('hidden');
        return;
    }
    dom.graphEmpty.classList.add('hidden');

    const svg = d3.select(container)
        .append('svg')
        .attr('class', 'graph-svg')
        .attr('width', width)
        .attr('height', height);

    // tooltip
    const tooltip = d3.select(container)
        .append('div')
        .attr('class', 'graph-tooltip');

    // 缩放
    const g = svg.append('g');
    const zoom = d3.zoom()
        .scaleExtent([0.3, 3])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });
    svg.call(zoom);

    g.append('text')
        .attr('x', 24)
        .attr('y', 34)
        .attr('font-size', '14px')
        .attr('font-weight', '600')
        .attr('fill', '#334155')
        .text(`中心：${getGraphCenterLabels().join('、') || '未确认委托人'}`);

    // 准备数据副本（避免修改原始数据）
    const nodes = visibleNodes.map(n => ({ ...n }));
    const edges = visibleEdges.map(e => ({ ...e }));
    nodes.forEach(node => {
        if (isGraphCenterLabel(node.label)) {
            node.x = width / 2;
            node.y = height / 2;
            node.fx = width / 2;
            node.fy = height / 2;
        }
    });

    // 力导向模拟
    const simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(edges)
            .id(d => d.id)
            .distance(d => d.distance || 135))
        .force('charge', d3.forceManyBody().strength(-360))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => getNodeRadius(d) + 8));

    state.graphSimulation = simulation;

    // 边
    const linkGroup = g.append('g').attr('class', 'links');
    const link = linkGroup.selectAll('line')
        .data(edges)
        .enter()
        .append('line')
        .attr('stroke', '#94a3b8')
        .attr('stroke-width', d => d.width || 1.5)
        .attr('stroke-opacity', 0.6)
        .attr('stroke-dasharray', d => d.style === 'dashed' ? '5,5' : 'none');

    // 边标签
    const edgeLabelGroup = g.append('g').attr('class', 'edge-labels');
    const edgeLabels = edgeLabelGroup.selectAll('text')
        .data(edges.filter(e => e.label))
        .enter()
        .append('text')
        .attr('font-size', '10px')
        .attr('fill', '#64748b')
        .attr('text-anchor', 'middle')
        .attr('dy', -3)
        .text(d => d.label);

    // 节点组
    const nodeGroup = g.append('g').attr('class', 'nodes');
    const node = nodeGroup.selectAll('g')
        .data(nodes)
        .enter()
        .append('g')
        .attr('cursor', 'pointer')
        .call(d3.drag()
            .on('start', (event, d) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on('drag', (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
            })
            .on('end', (event, d) => {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = isGraphCenterLabel(d.label) ? d.x : null;
                d.fy = isGraphCenterLabel(d.label) ? d.y : null;
            }));

    // 节点圆圈
    node.append('circle')
        .attr('r', d => getNodeRadius(d))
        .attr('fill', d => isGraphCenterLabel(d.label) ? '#059669' : getNodeColor(d.type))
        .attr('stroke', '#fff')
        .attr('stroke-width', 2)
        .attr('opacity', 0.9);

    // 节点标签
    node.append('text')
        .attr('dy', d => getNodeRadius(d) + 14)
        .attr('text-anchor', 'middle')
        .attr('font-size', '11px')
        .attr('fill', '#334155')
        .attr('font-weight', d => isGraphCenterLabel(d.label) || d.importance === 'primary' ? '600' : '400')
        .text(d => d.label);

    // 悬停tooltip
    node.on('mouseenter', (event, d) => {
        const title = safeGraphText(d.label);
        const description = safeGraphText(d.description);
        tooltip.html(`<strong>${escapeHtml(title)}</strong>${description ? '<br>' + escapeHtml(description) : ''}`);
        tooltip.classed('visible', true);
    })
    .on('mousemove', (event) => {
        const rect = container.getBoundingClientRect();
        tooltip
            .style('left', (event.clientX - rect.left + 12) + 'px')
            .style('top', (event.clientY - rect.top - 8) + 'px');
    })
    .on('mouseleave', () => {
        tooltip.classed('visible', false);
    });

    // tick
    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        edgeLabels
            .attr('x', d => (d.source.x + d.target.x) / 2)
            .attr('y', d => (d.source.y + d.target.y) / 2);

        node.attr('transform', d => `translate(${d.x},${d.y})`);
    });
}

// ============================
// 起诉书视图
// ============================

async function loadIndictmentView() {
    if (!state.indictment) {
        try {
            const data = await API.getIndictment(state.currentCase);
            state.indictment = data;
        } catch (e) {
            state.indictment = { has_indictment: false };
        }
    }

    if (!state.indictment.has_indictment) {
        dom.indictmentEmpty.classList.remove('hidden');
        dom.indictmentContent.classList.add('hidden');
        return;
    }

    dom.indictmentEmpty.classList.add('hidden');
    dom.indictmentContent.classList.remove('hidden');

    // 结构化信息卡片
    const structured = state.indictment.structured || {};
    const cards = [];
    if (structured.文书类型) cards.push({ label: '文书类型', value: structured.文书类型 });
    if (structured.案件编号) cards.push({ label: '案件编号', value: structured.案件编号 });
    if (structured.案件名称) cards.push({ label: '案件名称', value: structured.案件名称 });
    if (structured.当事人) cards.push({ label: '当事人', value: structured.当事人 });
    if (structured.罪名) cards.push({ label: '罪名', value: structured.罪名 });
    if (structured.涉案金额) cards.push({ label: '涉案金额', value: structured.涉案金额 });
    if (structured.案件事实 || structured.犯罪事实) {
        cards.push({ label: '案件事实', value: structured.案件事实 || structured.犯罪事实 });
    }
    if (structured.其他关键信息) cards.push({ label: '其他关键信息', value: structured.其他关键信息 });
    if (structured.证据列表 && structured.证据列表.length) {
        cards.push({ label: '证据列表', value: structured.证据列表 });
    }
    if (structured.适用法律 && structured.适用法律.length) {
        cards.push({ label: '适用法律', value: structured.适用法律 });
    }
    if (structured.量刑建议) cards.push({ label: '量刑建议', value: structured.量刑建议 });
    if (structured.起诉机关) cards.push({ label: '起诉机关', value: structured.起诉机关 });
    if (structured.起诉日期) cards.push({ label: '起诉日期', value: structured.起诉日期 });

    if (cards.length === 0) {
        dom.indictmentStructured.innerHTML = '';
    } else {
        dom.indictmentStructured.innerHTML = cards.map(c => `
            <div class="indictment-info-card">
                <div class="info-label">${escapeHtml(c.label)}</div>
                <div class="info-value">${escapeHtml(formatDisplayValue(c.value))}</div>
            </div>
        `).join('');
    }

    // 原文
    dom.indictmentOriginal.textContent = state.indictment.content || '无内容';
    dom.indictmentOriginal.classList.add('hidden');
    dom.toggleOriginalText.textContent = '展开原文';
}

function toggleIndictmentOriginal() {
    const isHidden = dom.indictmentOriginal.classList.contains('hidden');
    dom.indictmentOriginal.classList.toggle('hidden', !isHidden);
    dom.toggleOriginalText.textContent = isHidden ? '收起原文' : '展开原文';
}

// ============================
// 材料处理与 AI 工作台
// ============================

async function loadAIView() {
    await Promise.all([
        loadAISettings(),
        loadGraphRAGStatus(),
        loadChatHistory(),
    ]);
    renderGraphRAGPanel();
    renderChatMessages();
}

async function loadAISettings() {
    try {
        state.aiSettings = await API.getAISettings();
        renderAISettings();
    } catch (e) {
        showToast('AI 配置读取失败');
    }
}

function renderAISettings() {
    const settings = state.aiSettings || {};
    setProfileForm('strong', settings.strong || {});
    setProfileForm('cheap', settings.cheap || {});
    const routing = settings.routing || {};
    dom.routeChatDefault.value = routing.chat_default || 'strong';
    dom.routeExtractDefault.value = routing.extract_default || 'cheap';
    dom.routeReviewDefault.value = routing.review_default || 'strong';
    dom.chatProfile.value = routing.chat_default || 'strong';
    if (dom.companionProfile) dom.companionProfile.value = routing.chat_default || 'strong';
    const mineru = settings.mineru || {};
    dom.mineruApiToken.value = '';
    dom.mineruApiToken.placeholder = mineru.has_api_token ? '已保存，留空不修改' : '必须配置 MinerU Token';
    dom.mineruPollInterval.value = mineru.poll_interval_seconds || 3;
    dom.mineruTimeout.value = mineru.timeout_seconds || 600;
}

function setProfileForm(profile, config) {
    const prefix = profile === 'strong' ? 'strong' : 'cheap';
    dom[`${prefix}Protocol`].value = config.protocol || 'openai';
    dom[`${prefix}BaseUrl`].value = config.base_url || '';
    dom[`${prefix}Model`].value = config.model || '';
    dom[`${prefix}ApiKey`].value = '';
    dom[`${prefix}ApiKey`].placeholder = config.has_api_key ? '已保存，留空不修改' : '留空表示不配置';
}

function collectProfileForm(prefix) {
    const profile = {
        protocol: dom[`${prefix}Protocol`].value,
        base_url: dom[`${prefix}BaseUrl`].value.trim(),
        model: dom[`${prefix}Model`].value.trim(),
    };
    const apiKey = dom[`${prefix}ApiKey`].value.trim();
    if (apiKey) profile.api_key = apiKey;
    return profile;
}

async function saveAISettings() {
    dom.btnSaveAISettings.disabled = true;
    dom.btnSaveAISettings.textContent = '保存中...';
    try {
        state.aiSettings = await API.saveAISettings({
            strong: collectProfileForm('strong'),
            cheap: collectProfileForm('cheap'),
            routing: {
                chat_default: dom.routeChatDefault.value,
                extract_default: dom.routeExtractDefault.value,
                review_default: dom.routeReviewDefault.value,
            },
            mineru: collectMinerUForm(),
        });
        renderAISettings();
        showToast('AI 配置已保存');
    } catch (e) {
        showToast('AI 配置保存失败');
    } finally {
        dom.btnSaveAISettings.disabled = false;
        dom.btnSaveAISettings.textContent = '保存 AI 配置';
    }
}

function collectMinerUForm() {
    const mineru = {
        base_url: 'https://mineru.net',
        poll_interval_seconds: Number(dom.mineruPollInterval.value || 3),
        timeout_seconds: Number(dom.mineruTimeout.value || 600),
    };
    const apiToken = dom.mineruApiToken.value.trim();
    if (apiToken) mineru.api_token = apiToken;
    return mineru;
}

async function testAI(profile) {
    const btn = profile === 'strong' ? dom.btnTestStrongAI : dom.btnTestCheapAI;
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = '测试中...';
    try {
        const prefix = profile === 'strong' ? 'strong' : 'cheap';
        const data = await API.testAI(profile, collectProfileForm(prefix));
        showToast(data.ok ? `${profile === 'strong' ? '强 AI' : '弱 AI'}：${data.message}` : data.error);
    } catch (e) {
        showToast('连接测试失败');
    } finally {
        btn.disabled = false;
        btn.textContent = original;
    }
}




async function loadGraphRAGStatus() {
    if (!state.currentCase) return;
    try {
        state.graphragStatus = await API.getGraphRAGIndex(state.currentCase);
    } catch (e) {
        state.graphragStatus = null;
    }
}

function renderGraphRAGPanel() {
    if (!dom.graphragStatus) return;
    const status = state.graphragStatus || {};
    const summary = status.summary || {};
    if (status.error) {
        dom.graphragStatus.innerHTML = `<div class="graphrag-empty">${escapeHtml(status.error)}</div>`;
    } else {
        dom.graphragStatus.innerHTML = `
            <div class="graphrag-stat"><strong>${Number(summary.document_count || 0)}</strong><span>材料</span></div>
            <div class="graphrag-stat"><strong>${Number(summary.chunk_count || 0)}</strong><span>证据片段</span></div>
            <div class="graphrag-stat"><strong>${Number(summary.node_count || 0)}</strong><span>节点</span></div>
            <div class="graphrag-stat"><strong>${Number(summary.edge_count || 0)}</strong><span>关系</span></div>
        `;
    }
    renderGraphRAGResults();
}

function renderGraphRAGResults() {
    if (!dom.graphragResults) return;
    const retrieval = state.graphragRetrieval;
    if (!retrieval) {
        dom.graphragResults.innerHTML = '<div class="graphrag-empty">暂无检索结果。</div>';
        return;
    }
    const chunks = retrieval.chunks || [];
    const edges = retrieval.edges || [];
    const chunkHtml = chunks.slice(0, 5).map((chunk, index) => `
        <div class="graphrag-result">
            <div class="graphrag-result-title">E${index + 1} · ${escapeHtml(chunk.citation || chunk.source_title || chunk.id)}</div>
            <div class="graphrag-result-text">${escapeHtml((chunk.text || '').slice(0, 260))}${(chunk.text || '').length > 260 ? '...' : ''}</div>
        </div>
    `).join('');
    const edgeHtml = edges.slice(0, 4).map(edge => `
        <div class="graphrag-edge">
            ${escapeHtml(edge.source_label || edge.source)} → ${escapeHtml(edge.target_label || edge.target)}：${escapeHtml(edge.label || '')}
        </div>
    `).join('');
    dom.graphragResults.innerHTML = `
        ${chunkHtml || '<div class="graphrag-empty">没有命中证据片段。</div>'}
        ${edgeHtml ? `<div class="graphrag-edge-list">${edgeHtml}</div>` : ''}
    `;
}

async function rebuildGraphRAGIndex() {
    if (!state.currentCase) return;
    const original = dom.btnRebuildGraphRAG.textContent;
    dom.btnRebuildGraphRAG.disabled = true;
    dom.btnRebuildGraphRAG.textContent = '重建中...';
    try {
        state.graphragStatus = await API.rebuildGraphRAG(state.currentCase);
        state.graphragRetrieval = null;
        renderGraphRAGPanel();
        showToast('GraphRAG 索引已重建');
    } catch (e) {
        showToast('GraphRAG 索引重建失败');
    } finally {
        dom.btnRebuildGraphRAG.disabled = false;
        dom.btnRebuildGraphRAG.textContent = original;
    }
}

async function testGraphRAGRetrieval() {
    const query = dom.graphragQuery.value.trim();
    if (!query) {
        showToast('请输入检索问题');
        return;
    }
    const original = dom.btnTestGraphRAG.textContent;
    dom.btnTestGraphRAG.disabled = true;
    dom.btnTestGraphRAG.textContent = '检索中...';
    try {
        const data = await API.retrieveGraphRAG(state.currentCase, query, 5);
        if (data.error) {
            showToast(data.error);
            return;
        }
        state.graphragRetrieval = data.retrieval || null;
        renderGraphRAGResults();
    } catch (e) {
        showToast('GraphRAG 检索失败');
    } finally {
        dom.btnTestGraphRAG.disabled = false;
        dom.btnTestGraphRAG.textContent = original;
    }
}





function collectNewCaseSettingsPayload() {
    const payload = {};
    if (!dom.newCaseUseExistingConfig.checked) {
        payload.strong = {
            protocol: 'openai',
            base_url: dom.newStrongBaseUrl.value.trim(),
            model: dom.newStrongModel.value.trim(),
        };
        if (dom.newStrongApiKey.value.trim()) {
            payload.strong.api_key = dom.newStrongApiKey.value.trim();
        }
        payload.cheap = {
            protocol: 'openai',
            base_url: dom.newCheapBaseUrl.value.trim(),
            model: dom.newCheapModel.value.trim(),
        };
        if (dom.newCheapApiKey.value.trim()) {
            payload.cheap.api_key = dom.newCheapApiKey.value.trim();
        }
        payload.mineru = {
            base_url: 'https://mineru.net',
            poll_interval_seconds: 3,
            timeout_seconds: 600,
        };
        if (dom.newMineruApiToken.value.trim()) {
            payload.mineru.api_token = dom.newMineruApiToken.value.trim();
        }
    }
    return payload;
}

async function createCaseAndStartBuild() {
    const caseName = dom.newCaseName.value.trim();
    const rawPdf = dom.newCaseRawPdf.value.trim();
    const documentPdf = dom.newDocumentPdf ? dom.newDocumentPdf.value.trim() : '';
    if (!caseName) {
        showToast('请先填写案件名称');
        return;
    }
    if (!rawPdf) {
        showToast('请先选择证据卷 PDF');
        return;
    }
    if (!documentPdf) {
        showToast('请先选择起诉书/起诉意见书或文书卷 PDF');
        return;
    }
    const mineruHasToken = Boolean((state.aiSettings || {}).mineru && (state.aiSettings || {}).mineru.has_api_token);
    const enteringToken = Boolean(dom.newMineruApiToken && dom.newMineruApiToken.value.trim());
    if (!mineruHasToken && !enteringToken) {
        showToast('严肃案件必须配置 MinerU Token，不能使用低精度解析');
        return;
    }
    const usingExisting = dom.newCaseUseExistingConfig && dom.newCaseUseExistingConfig.checked;
    const hasExistingAI = Boolean(
        (state.aiSettings || {}).strong && (state.aiSettings || {}).strong.has_api_key &&
        (state.aiSettings || {}).cheap && (state.aiSettings || {}).cheap.has_api_key
    );
    if (!usingExisting || !hasExistingAI) {
        const strongUrl = (dom.newStrongBaseUrl || {}).value && dom.newStrongBaseUrl.value.trim();
        const strongModel = (dom.newStrongModel || {}).value && dom.newStrongModel.value.trim();
        const strongKey = (dom.newStrongApiKey || {}).value && dom.newStrongApiKey.value.trim();
        const cheapUrl = (dom.newCheapBaseUrl || {}).value && dom.newCheapBaseUrl.value.trim();
        const cheapModel = (dom.newCheapModel || {}).value && dom.newCheapModel.value.trim();
        const cheapKey = (dom.newCheapApiKey || {}).value && dom.newCheapApiKey.value.trim();
        const strongOk = strongUrl && strongModel && strongKey;
        const cheapOk = cheapUrl && cheapModel && cheapKey;
        if (!strongOk && !cheapOk) {
            showToast('请先配置强 AI 和弱 AI（Base URL + 模型 + API Key），后续摘要、图谱、聊天都需要 AI');
            return;
        }
        if (!strongOk) {
            showToast('请先配置强 AI（Base URL + 模型 + API Key），后续上下文生成、图谱复核和聊天都需要');
            return;
        }
        if (!cheapOk) {
            showToast('请先配置弱 AI（Base URL + 模型 + API Key），后续批量摘要和人物摘要都需要');
            return;
        }
    }
    const original = dom.btnCreateCaseStartBuild.textContent;
    dom.btnCreateCaseStartBuild.disabled = true;
    dom.btnCreateCaseStartBuild.textContent = '创建中...';
    try {
        const settingsPayload = collectNewCaseSettingsPayload();
        if (Object.keys(settingsPayload).length) {
            state.aiSettings = await API.saveAISettings(settingsPayload);
            renderAISettings();
        }
        const created = await API.createCase(caseName);
        if (created.error) {
            showToast(created.error);
            return;
        }
        await refreshCaseOptions();
        const caseId = created.case.id;
        const data = await API.startAutoMaterialBuild(caseId, {
            raw_pdf: rawPdf,
            case_name: caseName,
            document_pdf: documentPdf,
            document_type: dom.newDocumentType ? dom.newDocumentType.value : 'direct',
        });
        if (data.error) {
            showToast(data.error);
            return;
        }
        showBuildProgress(caseId, data.job ? data.job.id : '');
    } catch (e) {
        showToast('新建案件失败');
    } finally {
        dom.btnCreateCaseStartBuild.disabled = false;
        dom.btnCreateCaseStartBuild.textContent = original;
    }
}



async function pickPath(targetInput, mode, kind = '') {
    if (!targetInput) return;
    try {
        const data = mode === 'file' ? await API.pickFile(kind) : await API.pickDirectory();
        if (data.error) {
            showToast(data.error);
            return;
        }
        if (data.cancelled) return;
        targetInput.value = data.path || '';
    } catch (e) {
        showToast(mode === 'file' ? '文件选择失败' : '文件夹选择失败');
    }
}



async function loadChatHistory() {
    try {
        const data = await API.getChatHistory(state.currentCase);
        state.chatMessages = data.messages || [];
    } catch (e) {
        state.chatMessages = [];
    }
    renderCompanionMessages();
}

function renderChatMessages() {
    if (!dom.chatMessages) return;
    if (!state.chatMessages.length) {
        dom.chatMessages.innerHTML = '<div class="chat-empty">还没有聊天记录。可以先问：围绕委托人，哪些笔录最值得优先核对？</div>';
        return;
    }
    dom.chatMessages.innerHTML = state.chatMessages.map(item => {
        const cleanContent = (item.content || '').replace(/\n?\[(SAVE_RESULT|SAVE|BRIEF):[\s\S]*$/, '');
        return `
        <div class="chat-message ${item.role === 'user' ? 'is-user' : 'is-assistant'}">
            <div class="chat-role">${item.role === 'user' ? '我' : 'AI'} · ${escapeHtml(item.profile || '')}</div>
            <div class="chat-content">${renderMarkdown(cleanContent)}</div>
        </div>`;
    }).join('');
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

async function sendChat() {
    await _streamChat(
        dom.chatInput, dom.chatMessages, dom.chatProfile,
        dom.btnSendChat
    );
    renderCompanionMessages(); // keep companion in sync
    renderChatMessages();
}

async function openCompanion() {
    if (!dom.companionPanel) return;
    // 已打开则关闭
    if (!dom.companionPanel.classList.contains('hidden')) {
        closeCompanion();
        return;
    }
    if (dom.companionHint) dom.companionHint.style.display = 'none';

    // 自适应方向：上方空间够则向上，否则向下
    dom.companionPanel.classList.remove('hidden');
    const btnRect = dom.companionToggle.getBoundingClientRect();
    const panelTargetH = Math.min(660, window.innerHeight - 120);
    const spaceAbove = btnRect.top - 10;
    const spaceBelow = window.innerHeight - btnRect.bottom - 10;
    if (spaceAbove >= panelTargetH || spaceAbove >= spaceBelow) {
        dom.companionPanel.classList.add('dir-up');
        dom.companionPanel.classList.remove('dir-down');
    } else {
        dom.companionPanel.classList.add('dir-down');
        dom.companionPanel.classList.remove('dir-up');
    }

    if (!state.aiSettings) {
        await loadAISettings();
    }
    if (!state.chatMessages.length) {
        await loadChatHistory();
    } else {
        renderCompanionMessages();
    }
    if (dom.companionInput) dom.companionInput.focus();
}

function closeCompanion() {
    if (dom.companionPanel) dom.companionPanel.classList.add('hidden');
}

function renderCompanionMessages() {
    if (!dom.companionMessages) return;
    if (!state.chatMessages.length) {
        dom.companionMessages.innerHTML = '<div class="chat-empty">还没有聊天记录。小扣会自动带入当前案件上下文。</div>';
        return;
    }
    dom.companionMessages.innerHTML = state.chatMessages.map(item => {
        const cleanContent = (item.content || '').replace(/\n?\[(SAVE_RESULT|SAVE|BRIEF):[\s\S]*$/, '');
        if (item.role === 'system') {
            return `
            <div class="chat-message is-system">
                <div class="chat-role">系统</div>
                <div class="chat-content">${escapeHtml(cleanContent)}</div>
            </div>`;
        }
        return `
        <div class="chat-message ${item.role === 'user' ? 'is-user' : 'is-assistant'}">
            <div class="chat-role">${item.role === 'user' ? '我' : '小扣'} · ${escapeHtml(item.profile || '')}</div>
            <div class="chat-content">${renderMarkdown(cleanContent)}</div>
        </div>`;
    }).join('');
    dom.companionMessages.scrollTop = dom.companionMessages.scrollHeight;
}

async function sendCompanionChat() {
    await _streamChat(
        dom.companionInput, dom.companionMessages, dom.companionProfile,
        dom.btnCompanionSend
    );
    renderChatMessages();
}

// ── 思考气泡 / 流式输出 辅助函数 ──

async function _streamChat(inputEl, messagesEl, profileEl, sendBtn) {
    const message = inputEl.value.trim();
    if (!message) return;
    const entrusted = ((state.partyContext || {}).entrusted_parties || []).join('、');
    if (!entrusted) {
        showToast('请先确认委托人，再启动案件聊天');
        openCaseSetup();
        return;
    }

    const profile = profileEl.value;
    const userMsg = { role: 'user', content: message, profile: profile };
    state.chatMessages.push(userMsg);
    inputEl.value = '';

    // 渲染用户消息
    renderCompanionMessages();
    renderChatMessages();
    if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;

    // 插入思考气泡
    const thinkId = 'think-' + Date.now();
    const thinkHtml = buildThinkBubble(thinkId);
    if (messagesEl) {
        messagesEl.insertAdjacentHTML('beforeend', thinkHtml);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    const thinkEl = document.getElementById(thinkId);
    const timerEl = document.getElementById(thinkId + '-timer');
    const thinkStart = Date.now();
    const timerInterval = setInterval(() => {
        if (timerEl) {
            const elapsed = Math.floor((Date.now() - thinkStart) / 1000);
            timerEl.textContent = `已等待 ${elapsed}s`;
        }
    }, 1000);

    const stageEls = {
        retrieving: document.getElementById(thinkId + '-stage-retrieving'),
        thinking: document.getElementById(thinkId + '-stage-thinking'),
    };

    const btnOrig = sendBtn.textContent;
    sendBtn.disabled = true;
    sendBtn.textContent = '…';

    try {
        const resp = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case: state.currentCase, message, profile }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.error || `HTTP ${resp.status}`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullAnswer = '';
        let streamingMsgEl = null;
        let streamingContentEl = null;
        let eventType = '';
        let dataStr = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                // 空行 = 事件边界 → 触发累积的 event+data
                if (!line.trim()) {
                    if (eventType && dataStr) {
                        let payload;
                        try { payload = JSON.parse(dataStr); } catch (e) { payload = {}; }

                        if (eventType === 'stage') {
                            updateThinkStage(stageEls, payload.stage, payload.text, payload.count);
                        } else if (eventType === 'token') {
                            if (!streamingMsgEl) {
                                removeThinkBubble(thinkEl, thinkId);
                                clearInterval(timerInterval);
                                streamingMsgEl = createStreamingMessage();
                                streamingContentEl = streamingMsgEl.querySelector('.streaming-content');
                                if (messagesEl) messagesEl.appendChild(streamingMsgEl);
                            }
                            const token = payload.content || '';
                            fullAnswer += token;
                            if (streamingContentEl) streamingContentEl.textContent = fullAnswer;
                            if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
                        } else if (eventType === 'done') {
                            if (streamingMsgEl) {
                                finalizeStreamingMessage(streamingMsgEl);
                                streamingMsgEl.querySelector('.streaming-cursor').classList.add('is-done');
                            }
                            state.chatMessages.push({ role: 'assistant', content: fullAnswer, profile });
                            // 先等 loadChatHistory 完成（内部会调 renderCompanionMessages）
                            await loadChatHistory();
                            renderChatMessages();
                            await handleChatMarkers(fullAnswer, message);
                            // 在所有渲染完成后注入确认卡片，避免被 render 冲掉
                            if (payload.rebuild_requested) {
                                setTimeout(() => injectRebuildConfirm(payload.rebuild_reason || ''), 200);
                            }
                        } else if (eventType === 'error') {
                            removeThinkBubble(thinkEl, thinkId);
                            clearInterval(timerInterval);
                            showToast(payload.text || '模型请求失败');
                            if (streamingMsgEl) streamingMsgEl.remove();
                        }
                    }
                    eventType = '';
                    dataStr = '';
                    continue;
                }
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    dataStr = line.slice(6);
                }
            }
        }
        // 流正常结束但没有 done 事件
        if (streamingMsgEl) {
            finalizeStreamingMessage(streamingMsgEl);
            streamingMsgEl.querySelector('.streaming-cursor').classList.add('is-done');
            state.chatMessages.push({ role: 'assistant', content: fullAnswer, profile });
        }
        await loadChatHistory();
        renderCompanionMessages();
        renderChatMessages();
        await handleChatMarkers(fullAnswer, message);

    } catch (e) {
        removeThinkBubble(thinkEl, thinkId);
        clearInterval(timerInterval);
        const lastIdx = state.chatMessages.length - 1;
        if (lastIdx >= 0 && state.chatMessages[lastIdx].role === 'user') {
            state.chatMessages.pop();
        }
        showToast('发送失败: ' + (e.message || '未知错误'));
    } finally {
        clearInterval(timerInterval);
        sendBtn.disabled = false;
        sendBtn.textContent = btnOrig;
        if (inputEl) inputEl.focus();
    }
}

function buildThinkBubble(id) {
    return `
    <div class="think-bubble" id="${id}">
        <div class="think-meta">
            <span class="think-spinner"></span>
            <span class="think-label">小扣 · 思考中</span>
            <span class="think-timer" id="${id}-timer">已等待 0s</span>
        </div>
        <div class="think-stages">
            <div class="think-stage is-active" id="${id}-stage-retrieving">
                <span class="stage-icon"><span class="stage-dot"></span></span>
                <span>正在检索案件证据…</span>
            </div>
            <div class="think-stage is-pending" id="${id}-stage-thinking">
                <span class="stage-icon"><span class="stage-dot"></span></span>
                <span>模型正在分析中…</span>
            </div>
        </div>
    </div>`;
}

function updateThinkStage(stageEls, stage, text, count) {
    const order = ['retrieving', 'thinking'];
    const idx = order.indexOf(stage);
    for (let i = 0; i < order.length; i++) {
        const el = stageEls[order[i]];
        if (!el) continue;
        el.classList.remove('is-active', 'is-done', 'is-pending');
        if (i < idx) el.classList.add('is-done');
        else if (i === idx) el.classList.add('is-active');
        else el.classList.add('is-pending');
    }
}

function removeThinkBubble(el, id) {
    if (!el) return;
    el.classList.add('is-exiting');
    setTimeout(() => {
        const fresh = document.getElementById(id);
        if (fresh) fresh.remove();
    }, 200);
}

function createStreamingMessage() {
    const el = document.createElement('div');
    el.className = 'chat-message is-assistant is-streaming';
    el.innerHTML = `
        <div class="chat-role">小扣 · 分析中</div>
        <div class="chat-content">
            <span class="streaming-content"></span><span class="streaming-cursor"></span>
        </div>`;
    return el;
}

function finalizeStreamingMessage(el) {
    el.classList.remove('is-streaming');
    el.querySelector('.chat-role').textContent = el.querySelector('.chat-role').textContent.replace(' · 分析中', '');
    const cursor = el.querySelector('.streaming-cursor');
    if (cursor) cursor.classList.add('is-done');
}

function scrollCompanionBottom() {
    if (dom.companionMessages) {
        dom.companionMessages.scrollTop = dom.companionMessages.scrollHeight;
    }
}

function injectRebuildConfirm(reason) {
    if (!dom.companionMessages) return;
    // 防重复注入
    if (dom.companionMessages.querySelector('.rebuild-confirm')) return;
    const el = document.createElement('div');
    el.className = 'rebuild-confirm';
    el.innerHTML = `
        <div class="rebuild-confirm-icon">&#9888;</div>
        <div class="rebuild-confirm-text">
            <div class="rebuild-confirm-title">索引重建请求</div>
            <div class="rebuild-confirm-reason">${escapeHtml(reason)}</div>
        </div>
        <div class="rebuild-confirm-actions">
            <button class="rebuild-btn-confirm">确认重建</button>
            <button class="rebuild-btn-dismiss">忽略</button>
        </div>`;
    el.querySelector('.rebuild-btn-confirm').addEventListener('click', async () => {
        el.querySelector('.rebuild-confirm-actions').innerHTML = '<span class="rebuild-status">正在重建…</span>';
        try {
            const res = await fetch('/api/graphrag/rebuild', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ case: state.currentCase }),
            });
            const data = await res.json();
            if (data.summary) {
                el.querySelector('.rebuild-confirm-actions').innerHTML =
                    `<span class="rebuild-status done">已重建 · ${data.summary.chunk_count}块 ${data.summary.node_count}节点</span>`;
            } else {
                el.querySelector('.rebuild-confirm-actions').innerHTML =
                    '<span class="rebuild-status error">重建失败</span>';
            }
        } catch (e) {
            el.querySelector('.rebuild-confirm-actions').innerHTML =
                '<span class="rebuild-status error">请求失败</span>';
        }
    });
    el.querySelector('.rebuild-btn-dismiss').addEventListener('click', () => {
        el.querySelector('.rebuild-confirm-actions').innerHTML =
            '<span class="rebuild-status">已忽略</span>';
        el.style.opacity = '0.5';
    });
    dom.companionMessages.appendChild(el);
    dom.companionMessages.scrollTop = dom.companionMessages.scrollHeight;
}

async function handleChatMarkers(fullAnswer, originalQuestion) {
    const saveResultMatch = fullAnswer.match(/\[SAVE_RESULT:\s*title=([^,]+),\s*format=(md|csv|txt)\]/);
    const saveMatch = fullAnswer.match(/\[SAVE:\s*title=([^,]+),\s*format=(md|csv|txt)\]/);
    const activeSave = saveResultMatch || saveMatch;
    if (activeSave) {
        const contentBefore = fullAnswer.replace(/\[SAVE_RESULT:[\s\S]*$/, '').replace(/\[SAVE:[\s\S]*$/, '').trim();
        const title = activeSave[1].trim();
        const format = activeSave[2].trim();
        try {
            const saveResult = await API.saveAgentResult(state.currentCase, title, format, contentBefore);
            if (saveResult.ok) showToast(`已保存：${saveResult.filename}`);
        } catch (e) { /* ignore */ }
    }

    const updateMatch = fullAnswer.match(/\[UPDATE:\s*(.+?)(?:,\s*key=(.+))?\]/);
    if (updateMatch) {
        const contentBefore = fullAnswer.replace(/\[UPDATE:[\s\S]*$/, '').replace(/\[SAVE_RESULT:[\s\S]*$/, '').replace(/\[SAVE:[\s\S]*$/, '').trim();
        const field = updateMatch[1].trim();
        const key = (updateMatch[2] || '').trim();
        try {
            const upResult = await API.updateCaseField(state.currentCase, field, key, contentBefore);
            if (upResult.ok) {
                showToast(`已更新：${field}${key ? '（' + key + '）' : ''}`);
                if (field === '笔录摘要') await loadRecords();
                if (field === '人物摘要') await loadPersonSummaries();
                if (field === '案情图谱') { await loadGraph(true); renderGraph(); }
            }
        } catch (e) { /* ignore */ }
    }
}

async function pollAndFollowUpChat(jobId, originalQuestion) {
    const check = async () => {
        try {
            const res = await fetch(`/api/jobs/${jobId}`);
            const jobData = await res.json();
            const job = jobData.job || {};
            if (job.status === 'completed') {
                // 解析完成 → 自动追问小扣做分析
                const systemMsg = {
                    role: 'system',
                    content: `证据解析已完成。正在分析结果...`,
                    profile: 'system',
                };
                state.chatMessages.push(systemMsg);
                renderCompanionMessages();

                const followUp = `刚才解析的证据已经完成了。请根据这些证据内容，重新回答我之前的问题：「${originalQuestion}」。请引用具体证据的页码和内容。`;
                const data = await API.sendChat(state.currentCase, followUp, dom.companionProfile.value);
                if (!data.error) {
                    const content = data.message?.content || '';
                    // Strip markers from display
                    const cleanContent = content.replace(/\[PARSE_EVIDENCE:[\s\S]*$/, '').replace(/\[(SAVE_RESULT|SAVE|BRIEF):[\s\S]*$/, '').trim();
                    await loadChatHistory();
                    renderCompanionMessages();
                    renderChatMessages();
                }
                return;
            }
            if (job.status === 'failed') {
                const errMsg = {
                    role: 'system',
                    content: `证据解析失败: ${job.message}`,
                    profile: 'system',
                };
                state.chatMessages.push(errMsg);
                renderCompanionMessages();
                return;
            }
            // Still running, poll again
            setTimeout(check, 3000);
        } catch (e) {
            setTimeout(check, 5000);
        }
    };
    setTimeout(check, 2000);
}




// ============================
// 事件绑定
// ============================

function bindEvents() {
    // 启动封面
    dom.btnEntryNewCase.addEventListener('click', showNewCaseWizard);
    dom.btnEntryOldCase.addEventListener('click', showOldCaseChooser);
    if (dom.btnOpenTrash) dom.btnOpenTrash.addEventListener('click', openTrash);
    if (dom.btnBackFromTrash) dom.btnBackFromTrash.addEventListener('click', showOldCaseChooser);
    if (dom.btnEmptyTrash) dom.btnEmptyTrash.addEventListener('click', emptyTrash);
    dom.btnOpenNewCase.addEventListener('click', showNewCaseWizard);
    dom.newCaseUseExistingConfig.addEventListener('change', toggleNewCaseConfigFields);
    dom.btnPickNewCasePdf.addEventListener('click', () => pickPath(dom.newCaseRawPdf, 'file', 'pdf'));
    if (dom.btnPickNewDocumentPdf) {
        dom.btnPickNewDocumentPdf.addEventListener('click', () => pickPath(dom.newDocumentPdf, 'file', 'pdf'));
    }
    if (dom.newClientName) {
        dom.newClientName.addEventListener('input', () => {
            if (state.currentCase) loadNewClientCandidates(state.currentCase, dom.newClientName.value.trim());
        });
    }
    if (dom.newClientCandidateList) {
        dom.newClientCandidateList.addEventListener('click', e => {
            const btn = e.target.closest('[data-client-name]');
            if (!btn) return;
            dom.newClientName.value = btn.dataset.clientName || '';
        });
    }
    dom.btnCreateCaseStartBuild.addEventListener('click', createCaseAndStartBuild);
    if (dom.btnConfirmClient) dom.btnConfirmClient.addEventListener('click', confirmClient);
    if (dom.btnEnterWorkbench) dom.btnEnterWorkbench.addEventListener('click', enterWorkbench);
    dom.entryCaseList.addEventListener('click', e => {
        const item = e.target.closest('[data-entry-case]');
        if (item) enterExistingCase(item.dataset.entryCase);
    });

    // 案件切换
    dom.caseSelect.addEventListener('change', () => loadCase(dom.caseSelect.value));

    // 筛选（联动）
    [dom.filterName, dom.filterType, dom.filterDate].forEach(el => {
        el.addEventListener('change', applyFilters);
    });

    // 重置
    dom.btnReset.addEventListener('click', () => {
        dom.filterName.value = '';
        dom.filterType.value = '';
        dom.filterDate.value = '';
        dom.searchInput.value = '';
        state.searchKeywords = [];
        dom.searchStats.classList.add('hidden');
        applyFilters();
    });

    // 筛选面板折叠
    dom.btnToggleFilters.addEventListener('click', () => {
        dom.filtersPanel.classList.toggle('collapsed');
    });

    // 搜索
    dom.btnSearch.addEventListener('click', doSearch);
    dom.searchInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') doSearch();
    });

    // 视图切换
    dom.viewTabs.addEventListener('click', e => {
        const tab = e.target.closest('.view-tab');
        if (tab) {
            switchView(tab.dataset.view);
        }
    });

    // 笔录卡片点击
    dom.recordList.addEventListener('click', e => {
        const copyBtn = e.target.closest('.copy-btn');
        if (copyBtn) {
            e.stopPropagation();
            copyToClipboard(copyBtn.dataset.citation, copyBtn);
            return;
        }
        const card = e.target.closest('.record-card');
        if (card && card.dataset.id) {
            showRecord(card.dataset.id);
        }
    });

    // 人物卡片点击
    dom.personList.addEventListener('click', e => {
        const card = e.target.closest('.person-card');
        if (card) {
            togglePersonCard(card);
        }
    });

    // 当事人筛选
    dom.partyList.addEventListener('change', e => {
        if (e.target.matches('input[type="checkbox"]')) {
            updatePartyFilter();
        }
    });

    dom.btnSelectAllParties.addEventListener('click', selectAllParties);
    dom.btnOpenCaseSetup.addEventListener('click', openCaseSetup);
    dom.btnCloseCaseSetup.addEventListener('click', closeCaseSetup);
    dom.graphModeSwitch.addEventListener('click', e => {
        const btn = e.target.closest('.graph-mode-btn');
        if (!btn) return;
        state.graphMode = btn.dataset.graphMode;
        dom.graphModeSwitch.querySelectorAll('.graph-mode-btn').forEach(item => {
            item.classList.toggle('active', item === btn);
        });
        if (state.currentView === 'graph') renderGraph();
    });
    dom.partyContextOptions.addEventListener('change', renderPartyContextPreview);
    dom.btnSavePartyContext.addEventListener('click', savePartyContext);

    // 起诉书原文展开/收起
    dom.btnToggleOriginal.addEventListener('click', toggleIndictmentOriginal);

    // 证据材料视图
    const btnEvidenceSelectAll = document.getElementById('btn-evidence-select-all');
    const btnEvidenceDeselectAll = document.getElementById('btn-evidence-deselect-all');
    const btnEvidenceParse = document.getElementById('btn-evidence-parse');
    const evidenceTypeFilter = document.getElementById('evidence-type-filter');

    if (btnEvidenceSelectAll) btnEvidenceSelectAll.addEventListener('click', () => {
        for (const d of evidenceState.directory) {
            if (d['解析状态'] !== 'completed') evidenceState.selected.add(d.index);
        }
        renderEvidenceDirectory();
    });
    if (btnEvidenceDeselectAll) btnEvidenceDeselectAll.addEventListener('click', () => {
        evidenceState.selected.clear();
        renderEvidenceDirectory();
    });
    if (btnEvidenceParse) btnEvidenceParse.addEventListener('click', parseSelectedEvidence);
    if (evidenceTypeFilter) evidenceTypeFilter.addEventListener('change', () => renderEvidenceDirectory());

    // AI 配置、任务与聊天
    dom.btnSaveAISettings.addEventListener('click', saveAISettings);
    dom.btnTestStrongAI.addEventListener('click', () => testAI('strong'));
    dom.btnTestCheapAI.addEventListener('click', () => testAI('cheap'));
    dom.btnRebuildGraphRAG.addEventListener('click', rebuildGraphRAGIndex);
    dom.btnTestGraphRAG.addEventListener('click', testGraphRAGRetrieval);
    dom.graphragQuery.addEventListener('keydown', e => {
        if (e.key === 'Enter') testGraphRAGRetrieval();
    });
    dom.btnSendChat.addEventListener('click', sendChat);
    dom.chatInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChat();
        }
    });
    dom.companionToggle.addEventListener('click', openCompanion);
    dom.companionClose.addEventListener('click', closeCompanion);
    dom.btnCompanionSend.addEventListener('click', sendCompanionChat);
    // 小扣拖动
    if (dom.companionWidget && dom.companionToggle) {
        let dragState = null;
        dom.companionToggle.addEventListener('mousedown', e => {
            if (e.button !== 0) return;
            const rect = dom.companionWidget.getBoundingClientRect();
            dragState = { startX: e.clientX, startY: e.clientY, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top, moved: false };
            dom.companionToggle.classList.add('is-dragging');
        });
        document.addEventListener('mousemove', e => {
            if (!dragState) return;
            const dx = Math.abs(e.clientX - dragState.startX);
            const dy = Math.abs(e.clientY - dragState.startY);
            if (dx > 3 || dy > 3) dragState.moved = true;
            if (dragState.moved) {
                dom.companionWidget.style.right = 'auto';
                dom.companionWidget.style.bottom = 'auto';
                dom.companionWidget.style.left = (e.clientX - dragState.offsetX) + 'px';
                dom.companionWidget.style.top = (e.clientY - dragState.offsetY) + 'px';
            }
        });
        document.addEventListener('mouseup', () => {
            if (!dragState) return;
            dom.companionToggle.classList.remove('is-dragging');
            // 吸附到右边缘
            if (dragState.moved && dom.companionWidget.style.left) {
                const rect = dom.companionWidget.getBoundingClientRect();
                const winW = window.innerWidth;
                const snapRight = winW - rect.right;
                dom.companionWidget.style.left = 'auto';
                dom.companionWidget.style.right = Math.max(20, snapRight) + 'px';
            }
            const wasDrag = dragState.moved;
            dragState = null;
            // 拖动后阻止 click 触发
            if (wasDrag) {
                const stopClick = e => { e.stopPropagation(); e.stopImmediatePropagation(); dom.companionToggle.removeEventListener('click', stopClick, true); };
                dom.companionToggle.addEventListener('click', stopClick, true);
            }
        });
    }
    if (dom.btnBackToEntry) dom.btnBackToEntry.addEventListener('click', backToEntryCover);
    if (dom.btnOpenWorkspace) dom.btnOpenWorkspace.addEventListener('click', openWorkspace);
    dom.companionInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendCompanionChat();
        }
    });

    // 模态框关闭
    dom.modalClose.addEventListener('click', () => dom.modal.classList.add('hidden'));
    dom.modal.querySelector('.modal-overlay').addEventListener('click', () => dom.modal.classList.add('hidden'));
    dom.btnCopy.addEventListener('click', () => copyToClipboard(dom.btnCopy.dataset.citation, dom.btnCopy));

    // ESC关闭模态框
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') dom.modal.classList.add('hidden');
    });

    // 窗口大小变化时重绘图谱
    window.addEventListener('resize', debounce(() => {
        if (state.currentView === 'graph' && state.graph && state.graph.has_graph) {
            renderGraph();
        }
    }, 300));
}

function renderPartyContextPreview() {
    renderNameTags(dom.partyContextCurrent, getSelectedEntrustedParties(), '尚未确认委托人');
}

function debounce(fn, ms) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

async function doSearch() {
    const keyword = dom.searchInput.value.trim();
    if (!keyword) return;
    if (state.isSearching) return;

    state.searchKeywords = keyword.split(/\s+/).filter(Boolean);
    state.isSearching = true;

    dom.searchBtnText.classList.add('hidden');
    dom.searchBtnLoading.classList.remove('hidden');
    dom.btnSearch.disabled = true;
    dom.statusBar.textContent = '搜索中...';
    dom.searchStats.classList.add('hidden');

    try {
        const data = await API.search(state.currentCase, keyword);
        state.isSearchMode = true;

        dom.recordCount.textContent = `${data.total}条结果`;

        const nameFilter = data.name_filter || [];
        const contentKws = data.content_keywords || [];
        let statsHtml = '';

        if (nameFilter.length > 0 && contentKws.length > 0) {
            statsHtml = `已锁定 <strong>${escapeHtml(nameFilter.join('、'))}</strong> 的笔录（${data.total}份），` +
                `在其中搜索 <strong>${escapeHtml(contentKws.join(' '))}</strong>`;
        } else if (nameFilter.length > 0) {
            statsHtml = `已锁定 <strong>${escapeHtml(nameFilter.join('、'))}</strong> 的笔录，共 <strong>${data.total}</strong> 份`;
        } else {
            statsHtml = `找到 <strong>${data.total}</strong> 条相关笔录`;
        }
        dom.searchStats.innerHTML = statsHtml;
        dom.searchStats.classList.remove('hidden');

        dom.statusBar.textContent = `搜索 "${data.keyword}" 找到 ${data.total} 条结果`;
        renderRecords(data.results);
    } catch (err) {
        dom.statusBar.textContent = '搜索出错，请重试';
        console.error(err);
    } finally {
        state.isSearching = false;
        dom.searchBtnText.classList.remove('hidden');
        dom.searchBtnLoading.classList.add('hidden');
        dom.btnSearch.disabled = false;
    }
}

// ============================
// 新建向导：建库进度 → 委托人选择 → 分析进度
// ============================

async function showBuildProgress(caseId, jobId) {
    dom.entryNewPanel.classList.add('hidden');
    dom.entryBuildProgress.classList.remove('hidden');
    dom.entryClientSelect.classList.add('hidden');
    dom.entryAnalysisProgress.classList.add('hidden');

    // 记入 sessionStorage，刷新页面后自动恢复进度条
    try { sessionStorage.setItem('buildProgressCaseId', caseId); } catch (_) {}
    try { sessionStorage.setItem('buildProgressJobId', jobId); } catch (_) {}

    if (!jobId) {
        dom.buildProgressStage.textContent = '等待任务创建...';
        return;
    }

    const stageNames = {
        upload: '正在上传文件', directory_mineru: '正在 MinerU 解析目录',
        document_mineru: '正在 MinerU 解析文书材料', directory_parse: '正在解析目录结构',
        split_pdfs: '正在拆分笔录 PDF', record_mineru: '正在 MinerU OCR 识别笔录',
        validation: '正在校验数据', case_json: '正在生成案件数据',
        graphrag: '正在构建 GraphRAG 检索索引', completed: '建库完成',
    };

    const poll = async () => {
        try {
            const data = await API.getJob(caseId, jobId);
            const job = data.job || data;
            const status = job.status || 'running';
            const message = job.message || '';
            let manifestData = {};
            try {
                const mf = await API.getManifest(caseId, jobId);
                manifestData = mf.manifest || {};
            } catch (_) {}

            const stage = manifestData.stage || '';
            // 优先用 manifest 计算的进度（按阶段+子进度），fallback 到 job.progress
            const progress = (manifestData._progress != null) ? manifestData._progress : (job.progress || 0);

            if (dom.buildProgressFill) dom.buildProgressFill.style.width = progress + '%';

            // 主状态文本：显示当前阶段中文名
            const stageText = stageNames[stage] || (message || '处理中...');
            if (dom.buildProgressStage) dom.buildProgressStage.textContent = stageText;

            // 详情：显示阶段+大致进度
            if (dom.buildProgressDetail && stage) {
                dom.buildProgressDetail.textContent = `阶段 ${progress}%`;
            }

            if (status === 'completed') {
                try { sessionStorage.removeItem('buildProgressCaseId'); } catch (_) {}
                try { sessionStorage.removeItem('buildProgressJobId'); } catch (_) {}
                if (dom.buildProgressStage) dom.buildProgressStage.textContent = '建库完成！';
                if (dom.buildProgressDetail) dom.buildProgressDetail.textContent = '';
                if (dom.buildProgressFill) dom.buildProgressFill.style.width = '100%';
                const candidates = manifestData.party_candidates || [];
                showClientSelection(caseId, candidates);
                return;
            }
            if (status === 'failed') {
                try { sessionStorage.removeItem('buildProgressCaseId'); } catch (_) {}
                try { sessionStorage.removeItem('buildProgressJobId'); } catch (_) {}
                if (dom.buildProgressStage) dom.buildProgressStage.textContent = '建库失败：' + message;
                return;
            }
            setTimeout(poll, 3000);
        } catch (e) {
            if (dom.buildProgressStage) dom.buildProgressStage.textContent = '查询进度失败，重试中...';
            setTimeout(poll, 5000);
        }
    };
    poll();
}

function showClientSelection(caseId, candidates) {
    dom.entryBuildProgress.classList.add('hidden');
    dom.entryClientSelect.classList.remove('hidden');
    dom.entryAnalysisProgress.classList.add('hidden');

    state.pendingCaseId = caseId;
    state.pendingCandidates = candidates || [];

    if (dom.clientCandidateChips) {
        dom.clientCandidateChips.innerHTML = state.pendingCandidates.map(c => `
            <button type="button" class="client-candidate-chip" data-name="${escapeAttr(c.name)}">
                <span>${escapeHtml(c.name)}</span>
                <span class="chip-source">${escapeHtml(c.source || '')}</span>
            </button>
        `).join('');

        dom.clientCandidateChips.querySelectorAll('.client-candidate-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                dom.clientCandidateChips.querySelectorAll('.client-candidate-chip').forEach(c => c.classList.remove('selected'));
                chip.classList.add('selected');
                if (dom.confirmClientName) dom.confirmClientName.value = chip.dataset.name;
            });
        });
    }

    if (dom.confirmClientDatalist) {
        dom.confirmClientDatalist.innerHTML = state.pendingCandidates.map(c =>
            `<option value="${escapeAttr(c.name)}"></option>`
        ).join('');
    }

    if (dom.confirmClientName) dom.confirmClientName.value = '';
}

async function confirmClient() {
    const name = dom.confirmClientName ? dom.confirmClientName.value.trim() : '';
    if (!name) {
        showToast('请选择或输入委托人姓名');
        return;
    }
    const caseId = state.pendingCaseId;
    if (!caseId) {
        showToast('案件 ID 丢失，请刷新页面');
        return;
    }

    if (dom.btnConfirmClient) {
        dom.btnConfirmClient.disabled = true;
        dom.btnConfirmClient.textContent = '确认中...';
    }

    try {
        const data = await API.confirmClient(caseId, name);
        if (data.error) {
            showToast(data.error);
            return;
        }
        showAnalysisProgress(caseId, data.jobs || []);
    } catch (e) {
        showToast('确认委托人失败');
    } finally {
        if (dom.btnConfirmClient) {
            dom.btnConfirmClient.disabled = false;
            dom.btnConfirmClient.textContent = '确认委托人并开始分析';
        }
    }
}

async function showAnalysisProgress(caseId, jobs) {
    dom.entryClientSelect.classList.add('hidden');
    dom.entryAnalysisProgress.classList.remove('hidden');

    if (dom.btnEnterWorkbench) dom.btnEnterWorkbench.classList.add('hidden');
    if (dom.analysisSteps) {
        dom.analysisSteps.querySelectorAll('.analysis-step').forEach(step => {
            step.classList.remove('completed', 'running');
            const icon = step.querySelector('.analysis-step-icon');
            if (icon) icon.textContent = '○';
        });
    }

    const jobIds = jobs.map(j => j.id);
    const poll = async () => {
        try {
            const allJobs = await API.getJobs(caseId);
            const relevant = (allJobs.jobs || allJobs).filter(j => jobIds.includes(j.id));
            let allDone = true;
            let anyFailed = false;

            relevant.forEach(j => {
                const stepEl = dom.analysisSteps ? dom.analysisSteps.querySelector(`[data-step="${j.type}"]`) : null;
                if (!stepEl) return;
                const icon = stepEl.querySelector('.analysis-step-icon');
                if (j.status === 'completed') {
                    stepEl.classList.add('completed');
                    stepEl.classList.remove('running');
                    if (icon) icon.textContent = '✓';
                } else if (j.status === 'failed') {
                    stepEl.classList.add('completed');
                    stepEl.classList.remove('running');
                    if (icon) icon.textContent = '✗';
                    anyFailed = true;
                } else {
                    stepEl.classList.add('running');
                    stepEl.classList.remove('completed');
                    if (icon) icon.textContent = '◌';
                    allDone = false;
                }
            });

            if (allDone || anyFailed) {
                if (dom.btnEnterWorkbench) {
                    dom.btnEnterWorkbench.classList.remove('hidden');
                    dom.btnEnterWorkbench.textContent = anyFailed ? '部分分析失败，仍可进入工作台' : '进入工作台';
                }
                return;
            }
            setTimeout(poll, 3000);
        } catch (e) {
            setTimeout(poll, 5000);
        }
    };
    poll();
}

async function enterWorkbench() {
    const caseId = state.pendingCaseId;
    if (!caseId) {
        showToast('案件 ID 丢失');
        return;
    }
    dom.caseEntryCover.classList.add('hidden');
    dom.appShell.classList.remove('hidden');
    state.currentCase = caseId;
    await refreshCaseOptions();
    await loadCase(caseId);
    switchView('records');
}

async function openWorkspace() {
    await API.openWorkspace();
    showToast('已打开工作区');
}

async function backToEntryCover() {
    // 清空工作区，返回首页
    dom.appShell.classList.add('hidden');
    dom.caseEntryCover.classList.remove('hidden');
    dom.entryNewPanel.classList.add('hidden');
    dom.entryOldPanel.classList.add('hidden');
    dom.entryBuildProgress.classList.add('hidden');
    dom.entryClientSelect.classList.add('hidden');
    dom.entryAnalysisProgress.classList.add('hidden');
    dom.entryTrashPanel.classList.add('hidden');
    state.currentCase = null;
    state.pendingCaseId = null;
    await loadEntryCases();
    renderEntryCaseList();
}

// 启动
init();
