import { _ as _export_sfc, a as __mf_13, b as __mf_2, c as __mf_1, d as __mf_15, e as __mf_18, f as __mf_16, g as __mf_9, h as __mf_12, i as __mf_0, j as __mf_19, k as __mf_10, l as __mf_11 } from './_plugin-vue_export-helper-C3ZlwhxB.js';

const _hoisted_1 = { class: "eme-config" };
const _hoisted_2 = { class: "d-flex align-center mt-4" };

// 接收宿主能力：initialConfig 为已保存配置，api 为插件作用域客户端

const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const toast = __mf_13('moviepilot:toast', null);

const formRef = __mf_2(null);
const valid = __mf_2(true);
const optionsLoading = __mf_2(false);
const optionServers = __mf_2([]);
const optionLibraries = __mf_2([]);

// 默认值与后端 scanner.DEFAULT_CONFIG 对齐
const defaults = {
  enabled: false,
  notify: true,
  onlyonce: false,
  cron: '',
  servers: [],
  libraries: [],
  air_buffer_days: 1,
  include_specials: false,
  only_existing_seasons: true,
  max_series: 0,
};

const config = __mf_1({ ...defaults, ...(props.initialConfig || {}) });

const cronRules = [
  v => {
    const text = (v || '').trim();
    if (!text) return true
    return /^[\d*,\/-]+(\s+[\d*,\/-]+){4}$/.test(text) || '需要 5 位 cron 表达式，如 0 2 * * *'
  },
];

function apiBase() {
  return `plugin/${props.pluginId || 'EmbyMissingEpisodes'}`
}

async function loadOptions() {
  optionsLoading.value = true;
  try {
    const res = await props.api.get(`${apiBase()}/options`);
    const data = res?.success !== false ? res?.data || {} : {};
    if (Array.isArray(data.servers)) optionServers.value = data.servers;
    if (Array.isArray(data.libraries)) optionLibraries.value = data.libraries;
  } catch (err) {
    // 选项加载失败不阻塞配置编辑，仍可手动输入
    console.warn('加载 Emby 服务器选项失败:', err);
  } finally {
    optionsLoading.value = false;
  }
}

function save() {
  if (!valid.value) {
    toast?.warning('请先修正表单错误');
    return
  }
  // 保留 initialConfig 中的未知键（如 ignored 列表），仅覆盖表单字段
  emit('save', { ...(props.initialConfig || {}), ...config });
}

__mf_15(() => {
  loadOptions();
});

return (_ctx, _cache) => {
  const _component_v_switch = __mf_18("v-switch");
  const _component_v_col = __mf_18("v-col");
  const _component_v_text_field = __mf_18("v-text-field");
  const _component_v_row = __mf_18("v-row");
  const _component_v_select = __mf_18("v-select");
  const _component_v_combobox = __mf_18("v-combobox");
  const _component_v_alert = __mf_18("v-alert");
  const _component_v_form = __mf_18("v-form");
  const _component_v_btn = __mf_18("v-btn");
  const _component_v_spacer = __mf_18("v-spacer");

  return (__mf_16(), __mf_9("div", _hoisted_1, [
    __mf_12(_component_v_form, {
      ref_key: "formRef",
      ref: formRef,
      modelValue: valid.value,
      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((valid).value = $event)),
      onSubmit: __mf_0(save, ["prevent"])
    }, {
      default: __mf_19(() => [
        _cache[12] || (_cache[12] = __mf_10("div", { class: "text-subtitle-1 font-weight-bold mb-2" }, "基本设置", -1)),
        __mf_12(_component_v_row, null, {
          default: __mf_19(() => [
            __mf_12(_component_v_col, {
              cols: "12",
              md: "4"
            }, {
              default: __mf_19(() => [
                __mf_12(_component_v_switch, {
                  modelValue: config.enabled,
                  "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((config.enabled) = $event)),
                  label: "启用插件",
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            __mf_12(_component_v_col, {
              cols: "12",
              md: "4"
            }, {
              default: __mf_19(() => [
                __mf_12(_component_v_switch, {
                  modelValue: config.notify,
                  "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.notify) = $event)),
                  label: "扫描完成后通知",
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            __mf_12(_component_v_col, {
              cols: "12",
              md: "4"
            }, {
              default: __mf_19(() => [
                __mf_12(_component_v_switch, {
                  modelValue: config.onlyonce,
                  "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.onlyonce) = $event)),
                  label: "保存后立即扫描一次",
                  color: "primary",
                  hint: "仅本次保存时触发",
                  "persistent-hint": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            __mf_12(_component_v_col, {
              cols: "12",
              md: "4"
            }, {
              default: __mf_19(() => [
                __mf_12(_component_v_text_field, {
                  modelValue: config.cron,
                  "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.cron) = $event)),
                  label: "定时扫描周期",
                  placeholder: "5 位 cron 表达式，留空不定时",
                  rules: cronRules,
                  clearable: ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _cache[13] || (_cache[13] = __mf_10("div", { class: "text-subtitle-1 font-weight-bold mt-2 mb-2" }, "扫描范围", -1)),
        __mf_12(_component_v_row, null, {
          default: __mf_19(() => [
            __mf_12(_component_v_col, {
              cols: "12",
              md: "4"
            }, {
              default: __mf_19(() => [
                __mf_12(_component_v_select, {
                  modelValue: config.servers,
                  "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.servers) = $event)),
                  items: optionServers.value,
                  loading: optionsLoading.value,
                  label: "Emby 服务器",
                  multiple: "",
                  chips: "",
                  "closable-chips": "",
                  clearable: "",
                  hint: "留空表示全部已启用的 Emby 服务器",
                  "persistent-hint": ""
                }, null, 8, ["modelValue", "items", "loading"])
              ]),
              _: 1
            }),
            __mf_12(_component_v_col, {
              cols: "12",
              md: "4"
            }, {
              default: __mf_19(() => [
                __mf_12(_component_v_combobox, {
                  modelValue: config.libraries,
                  "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.libraries) = $event)),
                  items: optionLibraries.value,
                  loading: optionsLoading.value,
                  label: "媒体库名称",
                  multiple: "",
                  chips: "",
                  "closable-chips": "",
                  clearable: "",
                  hint: "留空表示全部电视剧库，可手动输入其他名称",
                  "persistent-hint": ""
                }, null, 8, ["modelValue", "items", "loading"])
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _cache[14] || (_cache[14] = __mf_10("div", { class: "text-subtitle-1 font-weight-bold mt-2 mb-2" }, "缺集判定", -1)),
        __mf_12(_component_v_row, null, {
          default: __mf_19(() => [
            __mf_12(_component_v_col, {
              cols: "12",
              md: "4"
            }, {
              default: __mf_19(() => [
                __mf_12(_component_v_text_field, {
                  modelValue: config.air_buffer_days,
                  "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.air_buffer_days) = $event)),
                  modelModifiers: { number: true },
                  type: "number",
                  min: "0",
                  label: "播出缓冲天数",
                  hint: "播出超过该天数才计入缺集",
                  "persistent-hint": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            __mf_12(_component_v_col, {
              cols: "12",
              md: "4"
            }, {
              default: __mf_19(() => [
                __mf_12(_component_v_switch, {
                  modelValue: config.include_specials,
                  "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.include_specials) = $event)),
                  label: "检查第 0 季（特别篇）",
                  color: "primary",
                  "hide-details": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            __mf_12(_component_v_col, {
              cols: "12",
              md: "4"
            }, {
              default: __mf_19(() => [
                __mf_12(_component_v_switch, {
                  modelValue: config.only_existing_seasons,
                  "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.only_existing_seasons) = $event)),
                  label: "只检查库中已有的季",
                  color: "primary",
                  hint: "关闭后整季缺失也会报告",
                  "persistent-hint": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            __mf_12(_component_v_col, {
              cols: "12",
              md: "4"
            }, {
              default: __mf_19(() => [
                __mf_12(_component_v_text_field, {
                  modelValue: config.max_series,
                  "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.max_series) = $event)),
                  modelModifiers: { number: true },
                  type: "number",
                  min: "0",
                  label: "单次扫描剧集上限",
                  hint: "0 表示不限制；达到上限时剩余剧集留到下次扫描",
                  "persistent-hint": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        __mf_12(_component_v_alert, {
          type: "info",
          variant: "tonal",
          density: "compact",
          class: "mt-2",
          text: "插件只读取媒体服务器的剧集季集与 TMDB 已播出集号，生成缺集报告，不会自动下载或订阅。报告页的「搜索」跳转 MoviePilot 搜索页，「订阅」按季添加订阅。"
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    __mf_10("div", _hoisted_2, [
      __mf_12(_component_v_btn, {
        variant: "text",
        color: "default",
        onClick: _cache[11] || (_cache[11] = $event => (emit('close')))
      }, {
        default: __mf_19(() => [...(_cache[15] || (_cache[15] = [
          __mf_11("关闭", -1)
        ]))]),
        _: 1
      }),
      __mf_12(_component_v_spacer),
      __mf_12(_component_v_btn, {
        color: "primary",
        disabled: !valid.value,
        onClick: save
      }, {
        default: __mf_19(() => [...(_cache[16] || (_cache[16] = [
          __mf_11("保存配置", -1)
        ]))]),
        _: 1
      }, 8, ["disabled"])
    ])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-f235dc6a"]]);

export { Config as default };
