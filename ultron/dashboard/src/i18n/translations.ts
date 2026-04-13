export type Locale = 'en' | 'zh';

interface Dict {
  [key: string]: string | Dict;
}

function isDict(v: string | Dict): v is Dict {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function walk(dict: Dict, path: string): string | undefined {
  const parts = path.split('.').filter(Boolean);
  let cur: string | Dict = dict;
  for (const p of parts) {
    if (!isDict(cur)) return undefined;
    cur = cur[p];
  }
  return typeof cur === 'string' ? cur : undefined;
}

const en: Dict = {
  nav: {
    memories: 'Memories',
    skills: 'Skills',
    leaderboard: 'Leaderboard',
    quickstart: 'Quickstart',
    harness: 'HarnessHub',
    github: 'Ultron on GitHub',
  },
  auth: {
    signedInAs: 'Signed in as',
    signOut: 'Sign Out',
    loading: 'Loading...',
    signInTitle: 'Sign in to use HarnessHub',
    createAccountTitle: 'Create an account to use HarnessHub',
    backWithoutSignIn: 'Continue without signing in',
    fillFields: 'Please fill in all fields',
    usernameMin: 'Username must be at least 3 characters',
    passwordMin: 'Password must be at least 6 characters',
    username: 'Username',
    password: 'Password',
    signIn: 'Sign In',
    createAccount: 'Create Account',
    noAccount: 'No account?',
    createOne: 'Create one',
    haveAccount: 'Already have an account?',
    signInLink: 'Sign in',
  },
  pagination: {
    prev: 'Prev',
    next: 'Next',
    pageOf: '{{page}} / {{pages}} ({{total}} total)',
  },
  dashboard: {
    title: 'Memories',
    totalMemories: 'Total Memories',
    hotHint: 'High-frequency memories',
    warmHint: 'Moderate activity',
    coldHint: 'Archived memories',
    internalSkills: 'Internal Skills',
    catalogSkills: 'Catalog Skills',
    searchPlaceholder: 'Search memories...',
    allTypes: 'All Types',
    allTiers: 'All Tiers',
    byHits: 'By Hits',
    byDate: 'By Date',
    empty: 'No memories found',
    hits: '{{n}} hits',
    kickerL0: 'L0 Summary',
    kickerL1: 'L1 Overview',
    fullContent: 'Full Content',
    context: 'Context',
    resolution: 'Resolution',
  },
  skills: {
    title: 'Skills',
    searchPlaceholder: 'Search skills...',
    allSources: 'All Sources',
    internal: 'Internal',
    sourceModelScope: 'ModelScope',
    allCategories: 'All Categories',
    empty: 'No skills found',
    openModelScope: 'Open on ModelScope',
    noDescription: 'No description',
    idLabel: 'ID',
  },
  leaderboard: {
    pageLoading: 'Loading leaderboard...',
    title: 'Hit Leaderboard',
    subtitle: 'Rankings by hit count within each tier',
    expandHint: 'Click a row to expand details',
    noData: 'No data',
    loading: 'Loading...',
    rowHits: '{{n}} hits',
  },
  harness: {
    title: 'HarnessHub',
    intro:
      'HarnessHub syncs your local Agent workspace with Ultron: upload workspace, view workspace, compose workspace, and share or import Agent configs via short codes.',
    ioLabelInput: 'Input',
    ioLabelOutput: 'Output',
    agentIdPlaceholder: 'Agent ID',
    copy: 'Copy',
    copied: 'Copied!',
    showcase: {
      kicker: 'Showcase',
      importTitle: 'One-click Import',
      example: 'Example',
      clickExample: '👉 Click here to see a FinanceBot example.',
    },
    upload: {
      kicker: 'Upload Workspace',
      detected: 'Detected',
      clickSelect: 'Click to select workspace folder',
      hintPaths: 'e.g.',
      selected: 'Selected',
      files: 'files',
      clearAll: 'Clear all',
      skipped:
        '{{n}} files skipped (not in allowlist, hidden, binary, or >1MB)',
      uploadToServer: 'Upload to Server',
      reading: 'Reading files...',
      uploading: 'Uploading {{n}} files...',
      uploadComplete:
        'Upload complete! {{files}} files synced (revision {{rev}}).',
      uploadFailed: 'Upload failed',
      agentId: 'Agent ID',
      alertUnrecognized:
        'Unrecognized workspace folder.\nPlease select ~/.nanobot, ~/.openclaw, or ~/.hermes',
      alertNoFiles: 'No files selected',
      input:
        'The local folder for your product.',
      output:
        'A new agent_id and the workspace files saved on the server.',
    },
    profile: {
      kicker: 'View Workspace',
      loadProfile: 'Load Profile',
      deleteAgent: 'Delete Agent',
      confirmDeleteAgent:
        'Remove this Agent from the server? This deletes the stored workspace profile and any share tokens for this Agent.',
      deleteFailed: 'Delete failed',
      product: 'Product',
      revision: 'Revision',
      updated: 'Updated',
      files: 'Files',
      input: 'An agent_id that already exists on the server.',
      output:
        'Product, last updated time, and a list of stored files.',
    },
    compose: {
      kicker: 'Compose Workspace',
      memories: 'Memories',
      skills: 'Skills',
      roles: 'Roles',
      role: 'Role',
      zodiac: 'Zodiac',
      selected: 'selected',
      searchMemories: 'Search memories...',
      searchSkills: 'Search skills...',
      searchRoles: 'Filter presets...',
      search: 'Search',
      hintMemories: 'Search to find memories',
      hintSkills: 'Search to find skills',
      hintRoles: 'Browse role presets',
      allCategories: 'All Categories',
      staging: 'Staging',
      items: 'items',
      apply: 'Apply to Profile',
      alertAgent: 'Select an Agent first',
      alertPick: 'Select at least one memory, skill, or role',
      statusBuilding: 'Building workspace profile...',
      statusUploading: 'Uploading to server...',
      statusDone:
        'Done! {{mem}} memories + {{skill}} skills + {{role}} roles applied (revision {{rev}}).',
      statusFailed: 'Failed',
      uploadFailed: 'Upload failed',
      hits: '{{n}} hits',
      input:
        'An agent_id, search queries, and the items you stage.',
      output:
        'Merged *.md written into that profile.',
    },
    share: {
      kicker: 'Share Agent',
      createShare: 'Create Share',
      noShares: 'No share tokens yet.',
      colCode: 'Code',
      colAgent: 'Agent',
      colCreated: 'Created',
      delete: 'Delete',
      confirmDelete: 'Delete this share token?',
      copyTitle: 'Click to copy short code',
      input:
        'The profile for the Agent you want to share.',
      output:
        'A share token and short code others can use to import.',
    },
    import: {
      kicker: 'Import Agent',
      shareCode: 'Share code',
      importTo: 'Import to',
      import: 'Import',
      warnOverwrite:
        'Importing overwrites your local workspace for the selected product. The installer backs up your current folder under ~/.ultron/harness-import-backups/ before writing, and prints the exact restore command when done.',
      runInTerminal: 'Run this command in your terminal:',
      input:
        'The share short code and the target product for import.',
      output:
        'A curl | bash one-liner you can run for one-click import.',
    },
  },
  quickstart: {
    title: 'Agent Setup',
    introPart1:
      'No need to install the Ultron source. Download the skill package, copy it into your Agent workspace, point ',
    introPart2: ' at this server, and let the Agent run setup from ',
    introPart3: '.',
    step1Title: 'Download the skill package',
    step1Desc:
      'Download the archive and unzip it on your machine. You should get an ultron-1.0.0 folder.',
    downloadZip: 'Download ultron-1.0.0.zip',
    zipHint: 'ZIP matches the repo layout below',
    packageContents: 'Package contents',
    step2Title: 'Install the skill and set the service URL',
    step2Desc:
      'Choose your Agent, run the copy command from the parent of the extracted folder, then set ULTRON_API_URL in your environment variables (for example with the export below).',
    agentWorkspace: 'Agent workspace',
    parentDirHint:
      'From the directory that contains the extracted ultron-1.0.0 folder (i.e. its parent), run:',
    apiEndpoint: 'Ultron API endpoint',
    step3Title: 'Let the Agent configure itself',
    step3Desc:
      'Send this to your Agent. It reads setup instructions and wires retrieval plus sync.',
    step3Code: 'Set up Ultron using setup.md',
    bullet1: 'Generates a unique ULTRON_AGENT_ID',
    bullet2: 'Adds retrieval guidance to SOUL.md',
    bullet3: 'Configures periodic session ingest',
    step4Title: 'Verify',
    step4Desc:
      "In your Agent's interactive session, send the prompt below. You should see retrieval and a reply that draws on Ultron memory.",
    step4Prompt: "I'm planning a trip to Kaifeng. Any suggestions?",
    step4Example: `You: I'm planning a trip to Kaifeng. Any suggestions?
  ↳ I'll help you retrieve suggestions for Kaifeng travel.
Based on memories retrieved from Ultron, here is a suggested Kaifeng travel guide...`,
    footer:
      'After setup, the Agent searches collective memory and skills before reasoning and syncs session experience back periodically.',
    docsLink: 'Agent setup docs →',
    copy: 'Copy',
    copied: 'Copied!',
  },
};

const zh: Dict = {
  nav: {
    memories: '记忆',
    skills: '技能',
    leaderboard: '排行榜',
    quickstart: '快速开始',
    harness: 'HarnessHub',
    github: 'Ultron GitHub 仓库',
  },
  auth: {
    signedInAs: '已登录为',
    signOut: '退出登录',
    loading: '加载中…',
    signInTitle: '登录以使用 HarnessHub',
    createAccountTitle: '注册账号以使用 HarnessHub',
    backWithoutSignIn: '暂不登录，返回应用',
    fillFields: '请填写所有字段',
    usernameMin: '用户名至少 3 个字符',
    passwordMin: '密码至少 6 个字符',
    username: '用户名',
    password: '密码',
    signIn: '登录',
    createAccount: '注册',
    noAccount: '没有账号？',
    createOne: '立即注册',
    haveAccount: '已有账号？',
    signInLink: '去登录',
  },
  pagination: {
    prev: '上一页',
    next: '下一页',
    pageOf: '{{page}} / {{pages}}（共 {{total}} 条）',
  },
  dashboard: {
    title: '记忆',
    totalMemories: '记忆总数',
    hotHint: '高频记忆',
    warmHint: '中等活跃',
    coldHint: '归档记忆',
    internalSkills: '内部技能',
    catalogSkills: '目录技能',
    searchPlaceholder: '搜索记忆…',
    allTypes: '全部类型',
    allTiers: '全部层级',
    byHits: '按命中',
    byDate: '按时间',
    empty: '暂无记忆',
    hits: '{{n}} 次命中',
    kickerL0: 'L0 摘要',
    kickerL1: 'L1 概览',
    fullContent: '全文',
    context: '上下文',
    resolution: '解决方案',
  },
  skills: {
    title: '技能',
    searchPlaceholder: '搜索技能…',
    allSources: '全部来源',
    internal: '内部',
    sourceModelScope: 'ModelScope',
    allCategories: '全部分类',
    empty: '暂无技能',
    openModelScope: '在 ModelScope 打开',
    noDescription: '无描述',
    idLabel: 'ID',
  },
  leaderboard: {
    pageLoading: '加载排行榜…',
    title: '命中排行榜',
    subtitle: '按层级内命中数排序',
    expandHint: '点击行展开详情',
    noData: '暂无数据',
    loading: '加载中…',
    rowHits: '{{n}} 次命中',
  },
  harness: {
    title: 'HarnessHub',
    intro:
      'HarnessHub 用于在本地 Agent 工作区与 Ultron 之间同步：上传工作区、查看工作区、合并工作区，并通过短码分享或导入 Agent 配置。',
    ioLabelInput: '输入',
    ioLabelOutput: '输出',
    agentIdPlaceholder: 'Agent ID',
    copy: '复制',
    copied: '已复制',
    showcase: {
      kicker: '案例展示',
      importTitle: '一键导入',
      example: '示例',
      clickExample: '👉 点击查看 FinanceBot 案例。',
    },
    upload: {
      kicker: '上传工作区',
      detected: '已识别',
      clickSelect: '点击选择工作区目录',
      hintPaths: '例如',
      selected: '已选',
      files: '个文件',
      clearAll: '清空',
      skipped: '已跳过 {{n}} 个文件（不在白名单、隐藏、二进制或超过 1MB）',
      uploadToServer: '上传到服务器',
      reading: '正在读取文件…',
      uploading: '正在上传 {{n}} 个文件…',
      uploadComplete: '上传完成！已同步 {{files}} 个文件（revision {{rev}}）。',
      uploadFailed: '上传失败',
      agentId: 'Agent ID',
      alertUnrecognized:
        '无法识别的工作区目录。\n请选择 ~/.nanobot、~/.openclaw 或 ~/.hermes',
      alertNoFiles: '未选择文件',
      input:
        '对应产品的本地目录（例如 ~/.nanobot、~/.openclaw、~/.hermes）。',
      output: '新的 agent_id（UUID）、该工作区在服务端保存的文件。',
    },
    profile: {
      kicker: '查看工作区',
      loadProfile: '加载 Profile',
      deleteAgent: '删除 Agent',
      confirmDeleteAgent:
        '从服务器上移除该 Agent？将删除已保存的工作区 profile 及该 Agent 的分享令牌。',
      deleteFailed: '删除失败',
      product: '产品',
      revision: '版本',
      updated: '更新时间',
      files: '文件数',
      input: '已在服务端存在的 agent_id（来自上传或下方列表）。',
      output: '产品、revision、更新时间，以及可展开查看的文件列表与文本预览。',
    },
    compose: {
      kicker: '合并工作区',
      memories: '记忆',
      skills: '技能',
      roles: '角色',
      role: '角色',
      zodiac: '星座',
      selected: '已选',
      searchMemories: '搜索记忆…',
      searchSkills: '搜索技能…',
      searchRoles: '筛选预设…',
      search: '搜索',
      hintMemories: '搜索以查找记忆',
      hintSkills: '搜索以查找技能',
      hintRoles: '浏览角色预设',
      allCategories: '全部分类',
      staging: '暂存',
      items: '项',
      apply: '应用到 Profile',
      alertAgent: '请先选择 Agent',
      alertPick: '请至少选择一条记忆、一个技能或一个角色',
      statusBuilding: '正在构建工作区 Profile…',
      statusUploading: '正在上传到服务器…',
      statusDone:
        '完成！已合并 {{mem}} 条记忆、{{skill}} 个技能与 {{role}} 个角色（revision {{rev}}）。',
      statusFailed: '失败',
      uploadFailed: '上传失败',
      hits: '{{n}} 次命中',
      input: 'agent_id，用于检索记忆与技能的搜索词，以及暂存区中选中的条目。',
      output: '合并后的 *.md 写入该 Profile 并上传。',
    },
    share: {
      kicker: '分享 Agent',
      createShare: '创建分享',
      noShares: '暂无分享令牌。',
      colCode: '短码',
      colAgent: 'Agent',
      colCreated: '创建时间',
      delete: '删除',
      confirmDelete: '确定删除该分享令牌？',
      copyTitle: '点击复制短码',
      input: '要分享的 Agent 对应的 Profile（默认公开）。',
      output: '供他人导入的分享令牌与短码，展示在下表中。',
    },
    import: {
      kicker: '导入 Agent',
      shareCode: '分享码',
      importTo: '导入到',
      import: '导入',
      warnOverwrite:
        '导入会覆盖所选产品在本机的工作区。安装脚本在写入前会把当前目录完整备份到 ~/.ultron/harness-import-backups/，结束后会在终端打印对应的恢复命令。',
      runInTerminal: '在终端中执行：',
      input: '分享短码，以及导入的目标产品（nanobot / openclaw / hermes）。',
      output: '可在本机执行的 curl | bash 一键导入命令。',
    },
  },
  quickstart: {
    title: 'Agent 配置',
    introPart1: '无需安装 Ultron。下载技能包放入 Agent 工作区，将 ',
    introPart2: ' 指向本服务，再让 Agent 根据 ',
    introPart3: ' 完成配置。',
    step1Title: '下载技能包',
    step1Desc: '下载压缩包并在本机解压，应得到 ultron-1.0.0 文件夹。',
    downloadZip: '下载 ultron-1.0.0.zip',
    zipHint: '与下方仓库目录结构一致',
    packageContents: '包内文件',
    step2Title: '安装技能并设置服务地址',
    step2Desc:
      '选择你的 Agent，在解压目录的上一级执行复制命令，再把 ULTRON_API_URL 写入环境变量（可使用下方 export 示例）。',
    agentWorkspace: 'Agent 工作区',
    parentDirHint: '在包含 ultron-1.0.0 文件夹的上一级目录执行：',
    apiEndpoint: 'Ultron API 地址',
    step3Title: '让 Agent 自行配置',
    step3Desc: '发给 Agent。它会读取安装说明并连接检索与同步。',
    step3Code: '使用 setup.md 配置 Ultron',
    bullet1: '生成唯一 ULTRON_AGENT_ID',
    bullet2: '在 SOUL.md 中加入检索指引',
    bullet3: '配置定期会话摄取',
    step4Title: '验证',
    step4Desc:
      '在 Agent 交互里发送下方提示，应看到检索与基于 Ultron 记忆的回复。',
    step4Prompt: "I'm planning a trip to Kaifeng. Any suggestions?",
    step4Example: `You: I'm planning a trip to Kaifeng. Any suggestions?
  ↳ I'll help you retrieve suggestions for Kaifeng travel.
Based on memories retrieved from Ultron, here is a suggested Kaifeng travel guide...`,
    footer: '配置完成后，Agent 会在推理前检索群体记忆与技能，并定期回写会话经验。',
    docsLink: 'Agent 配置文档 →',
    copy: '复制',
    copied: '已复制',
  },
};

const bundles: Record<Locale, Dict> = { en, zh };

export function lookupTranslation(locale: Locale, path: string): string {
  return walk(bundles[locale], path) ?? walk(bundles.en, path) ?? path;
}

export function formatTemplate(
  template: string,
  vars: Record<string, string | number>,
): string {
  let s = template;
  for (const [k, v] of Object.entries(vars)) {
    s = s.split(`{{${k}}}`).join(String(v));
  }
  return s;
}
