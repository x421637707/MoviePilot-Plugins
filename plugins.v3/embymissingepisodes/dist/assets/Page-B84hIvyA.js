import { _ as _export_sfc, a as __mf_13, b as __mf_2, m as __mf_6, n as __mf_14, d as __mf_15, e as __mf_18, f as __mf_16, g as __mf_9, o as __mf_7, p as __mf_5, q as __mf_8, j as __mf_19, k as __mf_10, h as __mf_12, r as __mf_4, s as __mf_17, l as __mf_11, t as __mf_3 } from './_plugin-vue_export-helper-C3ZlwhxB.js';

const __mfPromiseGlobalKey = "__mf_init__virtual:mf:__mfe_internal__EmbyMissingEpisodes__mf_owner__273637801637908__mf_v__runtimeInit__mf_v__.js__";
let __mfPromiseState = globalThis[__mfPromiseGlobalKey];
if (!__mfPromiseState) {
  let initResolve, initReject;
  const initPromise = new Promise((re, rj) => {
    initResolve = re;
    initReject = rj;
  });
  __mfPromiseState = globalThis[__mfPromiseGlobalKey] = {
    initPromise,
    initResolve,
    initReject,
  };
  
}
const initPromise = __mfPromiseState.initPromise;

    
const __mfCacheGlobalKey = "__mf_module_cache__";
globalThis[__mfCacheGlobalKey] ||= { share: {}, remote: {} };
globalThis[__mfCacheGlobalKey].share ||= {};
globalThis[__mfCacheGlobalKey].remote ||= {};
const __mfModuleCache = globalThis[__mfCacheGlobalKey];
const __mfTrackPendingShareLoad = (promise) => {
  const pendingShareLoads = (__mfModuleCache.pendingShareLoads ||= []);
  pendingShareLoads.push(promise);
  const cleanup = () => {
    const index = pendingShareLoads.indexOf(promise);
    if (index !== -1) pendingShareLoads.splice(index, 1);
  };
  void promise.then(cleanup, cleanup);
  return promise;
};
for (const __mfShareKey of Object.keys(__mfModuleCache.share)) {
  if (__mfShareKey.startsWith("default:")) {
    const __mfLegacyShareKey = __mfShareKey.slice("default:".length);
    if (__mfModuleCache.share[__mfLegacyShareKey] === undefined) {
      __mfModuleCache.share[__mfLegacyShareKey] = __mfModuleCache.share[__mfShareKey];
    }
  } else if (!__mfShareKey.includes(":")) {
    const __mfDefaultShareKey = "default:" + __mfShareKey;
    if (__mfModuleCache.share[__mfDefaultShareKey] === undefined) {
      __mfModuleCache.share[__mfDefaultShareKey] = __mfModuleCache.share[__mfShareKey];
    }
  }
}
          const __mfReadSharedCache = (cache, descriptor) => {
            const value = cache[descriptor.canonical];
            if (value !== undefined) return value;
            const aliases = descriptor.aliases || [];
            for (const alias of aliases) {
              if (!Object.prototype.hasOwnProperty.call(cache, alias)) continue;
              const aliasValue = cache[alias];
              if (aliasValue !== undefined) {
                cache[descriptor.canonical] = aliasValue;
                return aliasValue;
              }
            }
            return undefined;
          };
          const __mfSharedCacheListenersKey = Symbol.for("module-federation.shared-cache-listeners");
          const __mfGetSharedCacheListeners = (cache) => {
            let listeners = cache[__mfSharedCacheListenersKey];
            if (listeners === undefined) {
              listeners = Object.create(null);
              Object.defineProperty(cache, __mfSharedCacheListenersKey, {
                value: listeners,
                enumerable: false,
                configurable: false,
                writable: false
              });
            }
            return listeners;
          };
          const __mfSubscribeSharedCache = (cache, descriptor, listener) => {
            const listeners = __mfGetSharedCacheListeners(cache);
            (listeners[descriptor.canonical] ||= new Set()).add(listener);
          };
    let __mf_0;
    const __mfApplyHostProvidedExports = (exportModule) => {
      __mf_0 = exportModule["useDisplay"];
      exportModule.default ?? exportModule;
    };
    let exportModule = __mfReadSharedCache(__mfModuleCache.share, {"canonical":"default:vuetify","aliases":["vuetify"]});
    if (exportModule === undefined) {
      __mfSubscribeSharedCache(__mfModuleCache.share, {"canonical":"default:vuetify"}, (mod) => {
        exportModule = mod;
        __mfApplyHostProvidedExports(mod);
      });
      __mfTrackPendingShareLoad(initPromise.then(() => {
        exportModule = __mfReadSharedCache(__mfModuleCache.share, {"canonical":"default:vuetify","aliases":["vuetify"]});
        // A share init() left to its dynamic import is normally bridged before that import runs;
        // bridge it here when this wrapper is reached another way.
        if (exportModule === undefined && typeof __mfPromiseState.loadLazyShares === "function") {
          return __mfPromiseState.loadLazyShares(["vuetify"]).then(() => {
            exportModule = __mfReadSharedCache(__mfModuleCache.share, {"canonical":"default:vuetify","aliases":["vuetify"]});
          });
        }
      }).then(() => {
        if (exportModule === undefined) {
          throw new Error("[Module Federation] Shared module vuetify was imported before federation bootstrap finished.");
        }
        __mfApplyHostProvidedExports(exportModule);
      }));
    } else {
      __mfApplyHostProvidedExports(exportModule);
    }

const _hoisted_1 = { class: "eme-page" };
const _hoisted_2 = { class: "d-flex align-center ga-2" };
const _hoisted_3 = { class: "d-flex align-center flex-wrap ga-2 mb-3" };
const _hoisted_4 = { class: "py-1" };
const _hoisted_5 = {
  key: 1,
  class: "d-flex align-center justify-center rounded bg-grey-lighten-3 text-grey",
  style: {"height":"72px","width":"48px"}
};
const _hoisted_6 = {
  class: "py-1",
  style: {"min-width":"160px"}
};
const _hoisted_7 = { class: "font-weight-medium" };
const _hoisted_8 = {
  key: 0,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_9 = { class: "py-1" };
const _hoisted_10 = { class: "py-1" };
const _hoisted_11 = { class: "text-body-2" };
const _hoisted_12 = { class: "text-caption text-medium-emphasis" };
const _hoisted_13 = { class: "py-1" };
const _hoisted_14 = { class: "py-1" };
const _hoisted_15 = { class: "d-flex flex-wrap ga-1" };
const _hoisted_16 = {
  key: 2,
  class: "d-flex flex-column ga-2"
};
const _hoisted_17 = { class: "d-flex ga-3 pa-2" };
const _hoisted_18 = {
  key: 1,
  class: "d-flex align-center justify-center rounded bg-grey-lighten-3 text-grey flex-shrink-0",
  style: {"height":"72px","width":"48px"}
};
const _hoisted_19 = {
  class: "flex-grow-1",
  style: {"min-width":"0"}
};
const _hoisted_20 = { class: "font-weight-medium" };
const _hoisted_21 = {
  key: 0,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_22 = { class: "d-flex align-center flex-wrap ga-1 mt-1" };
const _hoisted_23 = { class: "text-body-2 mt-1" };
const _hoisted_24 = { class: "text-caption text-medium-emphasis" };
const _hoisted_25 = { class: "d-flex flex-wrap ga-1 mt-1" };
const _hoisted_26 = {
  key: 3,
  class: "text-caption pa-2 text-medium-emphasis"
};

// 接收宿主能力：api 为插件作用域客户端（返回 {success, message, data} 信封）
const ROW_LIMIT = 200;


const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  showSwitch: { type: Boolean, default: true },
},
  emits: ['action', 'switch', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const toast = __mf_13('moviepilot:toast', null);
const { mdAndUp } = __mf_0();

// 每个分组最多展示的行数
const loading = __mf_2(true);
const refreshing = __mf_2(false);
const scanning = __mf_2(false);
const error = __mf_2('');
const running = __mf_2(false);
const progress = __mf_2('');
const report = __mf_2(null);
const ignoredKeys = __mf_2([]);
const subscribedKeys = __mf_2([]);
// 标签页为纯客户端状态，切换即时生效
const tab = __mf_2('missing');
const busyKey = __mf_2('');
let pollTimer = null;

const shownErrors = __mf_6(() => (report.value?.errors || []).slice(0, 6));

const summaryText = __mf_6(() => {
  if (!report.value) return ''
  return (
    `最近扫描：${report.value.scanned_at || '-'}，共 ${report.value.series || 0} 部剧，` +
    `${allRows.value.length} 条缺集，耗时 ${report.value.duration || 0} 秒`
  )
});

const allRows = __mf_6(() => (report.value && Array.isArray(report.value.rows) ? report.value.rows : []));

const ignoredSet = __mf_6(() => new Set(ignoredKeys.value));
const subscribedSet = __mf_6(() => new Set(subscribedKeys.value));

const tabDefs = __mf_6(() => {
  const groups = { missing: [], subscribed: [], ignored: [] };
  for (const row of allRows.value) groups[statusOf(row)].push(row);
  return [
    { value: 'missing', label: '待处理', rows: groups.missing },
    { value: 'subscribed', label: '已订阅', rows: groups.subscribed },
    { value: 'ignored', label: '已忽略', rows: groups.ignored },
    { value: 'all', label: '全部', rows: allRows.value },
  ]
});

function apiBase() {
  return `plugin/${props.pluginId || 'EmbyMissingEpisodes'}`
}

function applyView(view) {
  running.value = !!view?.running;
  progress.value = view?.progress || '';
  report.value = view?.report || null;
  ignoredKeys.value = view?.ignored_keys || [];
  subscribedKeys.value = view?.subscribed_keys || [];
}

async function loadReport(silent = false) {
  if (!silent) loading.value = true;
  try {
    const res = await props.api.get(`${apiBase()}/report`);
    if (res && typeof res === 'object' && 'success' in res) {
      if (!res.success) {
        error.value = res.message || '加载报告失败';
        return
      }
      applyView(res.data);
    } else {
      applyView(res);
    }
    error.value = '';
  } catch (err) {
    error.value = err?.message || '加载报告失败';
  } finally {
    if (!silent) loading.value = false;
  }
}

async function refresh() {
  refreshing.value = true;
  await loadReport(false);
  refreshing.value = false;
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(async () => {
    await loadReport(true);
    if (!running.value) {
      stopPolling();
      toast?.success('扫描完成，报告已更新');
    }
  }, 3000);
}

__mf_14(stopPolling);

async function startScan() {
  scanning.value = true;
  try {
    const res = await props.api.post(`${apiBase()}/scan`, {});
    const ok = res?.success !== false;
    const message = res?.message || '';
    if (ok && res?.data?.queued !== false) {
      toast?.info(message || '已开始扫描');
      await loadReport(true);
      startPolling();
    } else {
      toast?.warning(message || '无法开始扫描');
    }
  } catch (err) {
    toast?.error(err?.message || '触发扫描失败');
  } finally {
    scanning.value = false;
  }
}

function rowKey(row) {
  return `${row?.media_id ?? ''}:${parseInt(row?.season || 0) || 0}`
}

function statusOf(row) {
  const key = rowKey(row);
  if (ignoredSet.value.has(key)) return 'ignored'
  if (subscribedSet.value.has(key)) return 'subscribed'
  return 'missing'
}

function statusMeta(row) {
  const map = {
    missing: { text: '缺集', color: 'error' },
    subscribed: { text: '已订阅', color: 'info' },
    ignored: { text: '已忽略', color: 'default' },
  };
  return map[statusOf(row)] || map.missing
}

function padSeason(row) {
  return String(parseInt(row?.season || 0) || 0).padStart(2, '0')
}

function rowTitle(row) {
  const title = String(row?.title || '');
  return row?.year ? `${title}（${row.year}）` : title
}

function rowLocation(row) {
  const server = String(row?.server || '');
  const library = String(row?.library || '');
  if (library) return server ? `${server} / ${library}` : library
  return server
}

function searchHref(row) {
  const title = encodeURIComponent(String(row?.title || ''));
  return `#/browse/media/search?title=${title}&type=media`
}

function episodeText(row) {
  const missing = (row?.missing || []).map(n => parseInt(n)).filter(n => !isNaN(n));
  if (!missing.length) return ''
  const fmt = n => `E${String(n).padStart(2, '0')}`;
  if (missing.length <= 12) return missing.map(fmt).join('、')
  return `${missing.slice(0, 12).map(fmt).join('、')} 等 ${missing.length} 集`
}

async function subscribeRow(row) {
  busyKey.value = rowKey(row) + ':sub';
  try {
    const res = await props.api.post(`${apiBase()}/subscribe`, {
      title: row?.title || '',
      year: row?.year || '',
      season: row?.season,
      media_source: row?.media_source || '',
      media_id: row?.media_id || '',
    });
    const ok = res?.success !== false;
    const message = res?.message || (ok ? '订阅成功' : '订阅未完成');
    ok ? toast?.success(message) : toast?.warning(message);
    await loadReport(true);
  } catch (err) {
    toast?.error(err?.message || '订阅失败');
  } finally {
    busyKey.value = '';
  }
}

async function toggleIgnore(row) {
  const ignored = statusOf(row) === 'ignored';
  busyKey.value = rowKey(row) + ':ign';
  try {
    const res = await props.api.post(`${apiBase()}/ignore`, {
      key: rowKey(row),
      title: row?.title || '',
      season: row?.season,
      remove: ignored,
    });
    const ok = res?.success !== false;
    const message = res?.message || (ignored ? '已取消忽略' : '已忽略');
    ok ? toast?.success(message) : toast?.warning(message);
    await loadReport(true);
  } catch (err) {
    toast?.error(err?.message || '操作失败');
  } finally {
    busyKey.value = '';
  }
}

__mf_15(async () => {
  await loadReport(false);
  if (running.value) startPolling();
});

return (_ctx, _cache) => {
  const _component_v_skeleton_loader = __mf_18("v-skeleton-loader");
  const _component_v_alert = __mf_18("v-alert");
  const _component_v_progress_circular = __mf_18("v-progress-circular");
  const _component_v_btn = __mf_18("v-btn");
  const _component_v_spacer = __mf_18("v-spacer");
  const _component_v_tab = __mf_18("v-tab");
  const _component_v_tabs = __mf_18("v-tabs");
  const _component_v_img = __mf_18("v-img");
  const _component_v_icon = __mf_18("v-icon");
  const _component_v_chip = __mf_18("v-chip");
  const _component_v_table = __mf_18("v-table");
  const _component_v_card = __mf_18("v-card");
  const _component_v_window_item = __mf_18("v-window-item");
  const _component_v_window = __mf_18("v-window");

  return (__mf_16(), __mf_9("div", _hoisted_1, [
    (loading.value && !report.value && !error.value)
      ? (__mf_16(), __mf_7(_component_v_skeleton_loader, {
          key: 0,
          type: "article, table"
        }))
      : (__mf_16(), __mf_9(__mf_5, { key: 1 }, [
          (error.value)
            ? (__mf_16(), __mf_7(_component_v_alert, {
                key: 0,
                type: "error",
                variant: "tonal",
                density: "compact",
                class: "mb-3",
                closable: "",
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => (error.value = '')),
                text: error.value
              }, null, 8, ["text"]))
            : __mf_8("", true),
          (running.value)
            ? (__mf_16(), __mf_7(_component_v_alert, {
                key: 1,
                type: "info",
                variant: "tonal",
                density: "compact",
                class: "mb-3"
              }, {
                default: __mf_19(() => [
                  __mf_10("div", _hoisted_2, [
                    __mf_12(_component_v_progress_circular, {
                      indeterminate: "",
                      size: "18",
                      width: "2"
                    }),
                    __mf_10("span", null, "正在扫描：" + __mf_4(progress.value || '准备中...'), 1)
                  ])
                ]),
                _: 1
              }))
            : __mf_8("", true),
          (report.value)
            ? (__mf_16(), __mf_7(_component_v_alert, {
                key: 2,
                type: allRows.value.length ? 'warning' : 'success',
                variant: "tonal",
                class: "mb-3",
                text: summaryText.value
              }, null, 8, ["type", "text"]))
            : (!error.value)
              ? (__mf_16(), __mf_7(_component_v_alert, {
                  key: 3,
                  type: "info",
                  variant: "tonal",
                  class: "mb-3",
                  text: "还没有扫描结果，点击「立即扫描」检查已挂载媒体库的缺集。"
                }))
              : __mf_8("", true),
          (report.value && report.value.cancelled)
            ? (__mf_16(), __mf_7(_component_v_alert, {
                key: 4,
                type: "info",
                variant: "tonal",
                density: "compact",
                class: "mb-2",
                text: "上一次扫描被中断，结果为部分数据。"
              }))
            : __mf_8("", true),
          (__mf_16(true), __mf_9(__mf_5, null, __mf_17(shownErrors.value, (item, index) => {
            return (__mf_16(), __mf_7(_component_v_alert, {
              key: index,
              type: "warning",
              variant: "tonal",
              density: "compact",
              class: "mb-2",
              text: item
            }, null, 8, ["text"]))
          }), 128)),
          __mf_10("div", _hoisted_3, [
            __mf_12(_component_v_btn, {
              color: "primary",
              variant: "flat",
              "prepend-icon": "mdi-magnify-scan",
              loading: scanning.value,
              disabled: running.value,
              onClick: startScan
            }, {
              default: __mf_19(() => [...(_cache[4] || (_cache[4] = [
                __mf_11("立即扫描", -1)
              ]))]),
              _: 1
            }, 8, ["loading", "disabled"]),
            __mf_12(_component_v_btn, {
              variant: "tonal",
              color: "default",
              "prepend-icon": "mdi-refresh",
              loading: refreshing.value,
              onClick: refresh
            }, {
              default: __mf_19(() => [...(_cache[5] || (_cache[5] = [
                __mf_11("刷新", -1)
              ]))]),
              _: 1
            }, 8, ["loading"]),
            __mf_12(_component_v_spacer),
            (__props.showSwitch)
              ? (__mf_16(), __mf_7(_component_v_btn, {
                  key: 0,
                  variant: "text",
                  color: "primary",
                  "prepend-icon": "mdi-cog",
                  onClick: _cache[1] || (_cache[1] = $event => (emit('switch')))
                }, {
                  default: __mf_19(() => [...(_cache[6] || (_cache[6] = [
                    __mf_11("配置", -1)
                  ]))]),
                  _: 1
                }))
              : __mf_8("", true)
          ]),
          (allRows.value.length)
            ? (__mf_16(), __mf_9(__mf_5, { key: 5 }, [
                __mf_12(_component_v_tabs, {
                  modelValue: tab.value,
                  "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((tab).value = $event)),
                  density: "compact",
                  color: "primary",
                  class: "mb-3"
                }, {
                  default: __mf_19(() => [
                    (__mf_16(true), __mf_9(__mf_5, null, __mf_17(tabDefs.value, (def) => {
                      return (__mf_16(), __mf_7(_component_v_tab, {
                        key: def.value,
                        value: def.value
                      }, {
                        default: __mf_19(() => [
                          __mf_11(__mf_4(def.label) + "（" + __mf_4(def.rows.length) + "） ", 1)
                        ]),
                        _: 2
                      }, 1032, ["value"]))
                    }), 128))
                  ]),
                  _: 1
                }, 8, ["modelValue"]),
                __mf_12(_component_v_window, {
                  modelValue: tab.value,
                  "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((tab).value = $event))
                }, {
                  default: __mf_19(() => [
                    (__mf_16(true), __mf_9(__mf_5, null, __mf_17(tabDefs.value, (def) => {
                      return (__mf_16(), __mf_7(_component_v_window_item, {
                        key: def.value,
                        value: def.value
                      }, {
                        default: __mf_19(() => [
                          (!def.rows.length)
                            ? (__mf_16(), __mf_7(_component_v_alert, {
                                key: 0,
                                type: "success",
                                variant: "tonal",
                                text: "该分组暂无条目。"
                              }))
                            : (__mf_3(mdAndUp))
                              ? (__mf_16(), __mf_7(_component_v_table, {
                                  key: 1,
                                  density: "compact",
                                  hover: ""
                                }, {
                                  default: __mf_19(() => [
                                    _cache[9] || (_cache[9] = __mf_10("thead", null, [
                                      __mf_10("tr", null, [
                                        __mf_10("th", { style: {"width":"64px"} }, "海报"),
                                        __mf_10("th", null, "媒体"),
                                        __mf_10("th", null, "季"),
                                        __mf_10("th", null, "缺失集"),
                                        __mf_10("th", null, "状态"),
                                        __mf_10("th", null, "操作")
                                      ])
                                    ], -1)),
                                    __mf_10("tbody", null, [
                                      (__mf_16(true), __mf_9(__mf_5, null, __mf_17(def.rows, (row) => {
                                        return (__mf_16(), __mf_9("tr", {
                                          key: def.value + '-' + rowKey(row) + '-' + row.server
                                        }, [
                                          __mf_10("td", _hoisted_4, [
                                            (row.poster)
                                              ? (__mf_16(), __mf_7(_component_v_img, {
                                                  key: 0,
                                                  src: row.poster,
                                                  height: "72",
                                                  width: "48",
                                                  "aspect-ratio": "2/3",
                                                  cover: "",
                                                  class: "rounded"
                                                }, null, 8, ["src"]))
                                              : (__mf_16(), __mf_9("div", _hoisted_5, [
                                                  __mf_12(_component_v_icon, {
                                                    icon: "mdi-television-classic-off",
                                                    size: "20"
                                                  })
                                                ]))
                                          ]),
                                          __mf_10("td", _hoisted_6, [
                                            __mf_10("div", _hoisted_7, __mf_4(rowTitle(row)), 1),
                                            (rowLocation(row))
                                              ? (__mf_16(), __mf_9("div", _hoisted_8, __mf_4(rowLocation(row)), 1))
                                              : __mf_8("", true)
                                          ]),
                                          __mf_10("td", _hoisted_9, [
                                            __mf_12(_component_v_chip, {
                                              size: "x-small",
                                              color: "primary",
                                              variant: "tonal"
                                            }, {
                                              default: __mf_19(() => [
                                                __mf_11("S" + __mf_4(padSeason(row)), 1)
                                              ]),
                                              _: 2
                                            }, 1024)
                                          ]),
                                          __mf_10("td", _hoisted_10, [
                                            __mf_10("div", _hoisted_11, __mf_4(episodeText(row)), 1),
                                            __mf_10("div", _hoisted_12, " 已播出 " + __mf_4(row.aired || 0) + " 集，库内 " + __mf_4(row.existing || 0) + " 集 ", 1)
                                          ]),
                                          __mf_10("td", _hoisted_13, [
                                            __mf_12(_component_v_chip, {
                                              size: "small",
                                              color: statusMeta(row).color,
                                              variant: "tonal"
                                            }, {
                                              default: __mf_19(() => [
                                                __mf_11(__mf_4(statusMeta(row).text), 1)
                                              ]),
                                              _: 2
                                            }, 1032, ["color"])
                                          ]),
                                          __mf_10("td", _hoisted_14, [
                                            __mf_10("div", _hoisted_15, [
                                              __mf_12(_component_v_btn, {
                                                size: "small",
                                                variant: "tonal",
                                                color: "primary",
                                                "prepend-icon": "mdi-magnify",
                                                href: searchHref(row)
                                              }, {
                                                default: __mf_19(() => [...(_cache[7] || (_cache[7] = [
                                                  __mf_11("搜索", -1)
                                                ]))]),
                                                _: 1
                                              }, 8, ["href"]),
                                              (statusOf(row) !== 'subscribed')
                                                ? (__mf_16(), __mf_7(_component_v_btn, {
                                                    key: 0,
                                                    size: "small",
                                                    variant: "tonal",
                                                    color: "secondary",
                                                    "prepend-icon": "mdi-bell-plus",
                                                    loading: busyKey.value === rowKey(row) + ':sub',
                                                    onClick: $event => (subscribeRow(row))
                                                  }, {
                                                    default: __mf_19(() => [...(_cache[8] || (_cache[8] = [
                                                      __mf_11("订阅本季", -1)
                                                    ]))]),
                                                    _: 1
                                                  }, 8, ["loading", "onClick"]))
                                                : __mf_8("", true),
                                              __mf_12(_component_v_btn, {
                                                size: "small",
                                                variant: "text",
                                                color: "default",
                                                "prepend-icon": statusOf(row) === 'ignored' ? 'mdi-undo' : 'mdi-eye-off-outline',
                                                loading: busyKey.value === rowKey(row) + ':ign',
                                                onClick: $event => (toggleIgnore(row))
                                              }, {
                                                default: __mf_19(() => [
                                                  __mf_11(__mf_4(statusOf(row) === 'ignored' ? '取消忽略' : '忽略'), 1)
                                                ]),
                                                _: 2
                                              }, 1032, ["prepend-icon", "loading", "onClick"])
                                            ])
                                          ])
                                        ]))
                                      }), 128))
                                    ])
                                  ]),
                                  _: 2
                                }, 1024))
                              : (__mf_16(), __mf_9("div", _hoisted_16, [
                                  (__mf_16(true), __mf_9(__mf_5, null, __mf_17(def.rows, (row) => {
                                    return (__mf_16(), __mf_7(_component_v_card, {
                                      key: def.value + '-' + rowKey(row) + '-' + row.server,
                                      variant: "outlined"
                                    }, {
                                      default: __mf_19(() => [
                                        __mf_10("div", _hoisted_17, [
                                          (row.poster)
                                            ? (__mf_16(), __mf_7(_component_v_img, {
                                                key: 0,
                                                src: row.poster,
                                                height: "72",
                                                width: "48",
                                                "aspect-ratio": "2/3",
                                                cover: "",
                                                class: "rounded flex-shrink-0 flex-grow-0"
                                              }, null, 8, ["src"]))
                                            : (__mf_16(), __mf_9("div", _hoisted_18, [
                                                __mf_12(_component_v_icon, {
                                                  icon: "mdi-television-classic-off",
                                                  size: "20"
                                                })
                                              ])),
                                          __mf_10("div", _hoisted_19, [
                                            __mf_10("div", _hoisted_20, __mf_4(rowTitle(row)), 1),
                                            (rowLocation(row))
                                              ? (__mf_16(), __mf_9("div", _hoisted_21, __mf_4(rowLocation(row)), 1))
                                              : __mf_8("", true),
                                            __mf_10("div", _hoisted_22, [
                                              __mf_12(_component_v_chip, {
                                                size: "x-small",
                                                color: "primary",
                                                variant: "tonal"
                                              }, {
                                                default: __mf_19(() => [
                                                  __mf_11("S" + __mf_4(padSeason(row)), 1)
                                                ]),
                                                _: 2
                                              }, 1024),
                                              __mf_12(_component_v_chip, {
                                                size: "x-small",
                                                color: statusMeta(row).color,
                                                variant: "tonal"
                                              }, {
                                                default: __mf_19(() => [
                                                  __mf_11(__mf_4(statusMeta(row).text), 1)
                                                ]),
                                                _: 2
                                              }, 1032, ["color"])
                                            ]),
                                            __mf_10("div", _hoisted_23, __mf_4(episodeText(row)), 1),
                                            __mf_10("div", _hoisted_24, " 已播出 " + __mf_4(row.aired || 0) + " 集，库内 " + __mf_4(row.existing || 0) + " 集 ", 1),
                                            __mf_10("div", _hoisted_25, [
                                              __mf_12(_component_v_btn, {
                                                size: "small",
                                                variant: "tonal",
                                                color: "primary",
                                                href: searchHref(row)
                                              }, {
                                                default: __mf_19(() => [...(_cache[10] || (_cache[10] = [
                                                  __mf_11("搜索", -1)
                                                ]))]),
                                                _: 1
                                              }, 8, ["href"]),
                                              (statusOf(row) !== 'subscribed')
                                                ? (__mf_16(), __mf_7(_component_v_btn, {
                                                    key: 0,
                                                    size: "small",
                                                    variant: "tonal",
                                                    color: "secondary",
                                                    loading: busyKey.value === rowKey(row) + ':sub',
                                                    onClick: $event => (subscribeRow(row))
                                                  }, {
                                                    default: __mf_19(() => [...(_cache[11] || (_cache[11] = [
                                                      __mf_11("订阅", -1)
                                                    ]))]),
                                                    _: 1
                                                  }, 8, ["loading", "onClick"]))
                                                : __mf_8("", true),
                                              __mf_12(_component_v_btn, {
                                                size: "small",
                                                variant: "text",
                                                color: "default",
                                                loading: busyKey.value === rowKey(row) + ':ign',
                                                onClick: $event => (toggleIgnore(row))
                                              }, {
                                                default: __mf_19(() => [
                                                  __mf_11(__mf_4(statusOf(row) === 'ignored' ? '取消忽略' : '忽略'), 1)
                                                ]),
                                                _: 2
                                              }, 1032, ["loading", "onClick"])
                                            ])
                                          ])
                                        ])
                                      ]),
                                      _: 2
                                    }, 1024))
                                  }), 128))
                                ])),
                          (def.rows.length > ROW_LIMIT)
                            ? (__mf_16(), __mf_9("div", _hoisted_26, " 仅显示前 " + __mf_4(ROW_LIMIT) + " 条，共 " + __mf_4(def.rows.length) + " 条。 ", 1))
                            : __mf_8("", true)
                        ]),
                        _: 2
                      }, 1032, ["value"]))
                    }), 128))
                  ]),
                  _: 1
                }, 8, ["modelValue"]),
                _cache[12] || (_cache[12] = __mf_10("div", { class: "text-caption pa-2 text-medium-emphasis" }, " 提示：订阅按季添加，实际补全由 MoviePilot 订阅流程完成；忽略只影响本插件报告展示，不会改动媒体库或订阅。 ", -1))
              ], 64))
            : __mf_8("", true)
        ], 64))
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-176b0f37"]]);

export { Page as default };
