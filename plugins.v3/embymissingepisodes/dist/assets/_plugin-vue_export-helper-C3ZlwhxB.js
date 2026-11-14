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
    let __mf_1;
    let __mf_2;
    let __mf_3;
    let __mf_4;
    let __mf_5;
    let __mf_6;
    let __mf_7;
    let __mf_8;
    let __mf_9;
    let __mf_10;
    let __mf_11;
    let __mf_12;
    let __mf_13;
    let __mf_14;
    let __mf_15;
    let __mf_16;
    let __mf_17;
    let __mf_18;
    let __mf_19;
    const __mfApplyHostProvidedExports = (exportModule) => {
      __mf_0 = exportModule["withModifiers"];
      __mf_1 = exportModule["reactive"];
      __mf_2 = exportModule["ref"];
      __mf_3 = exportModule["unref"];
      __mf_4 = exportModule["toDisplayString"];
      __mf_5 = exportModule["Fragment"];
      __mf_6 = exportModule["computed"];
      __mf_7 = exportModule["createBlock"];
      __mf_8 = exportModule["createCommentVNode"];
      __mf_9 = exportModule["createElementBlock"];
      __mf_10 = exportModule["createElementVNode"];
      __mf_11 = exportModule["createTextVNode"];
      __mf_12 = exportModule["createVNode"];
      __mf_13 = exportModule["inject"];
      __mf_14 = exportModule["onBeforeUnmount"];
      __mf_15 = exportModule["onMounted"];
      __mf_16 = exportModule["openBlock"];
      __mf_17 = exportModule["renderList"];
      __mf_18 = exportModule["resolveComponent"];
      __mf_19 = exportModule["withCtx"];
      exportModule.default ?? exportModule;
    };
    let exportModule = __mfReadSharedCache(__mfModuleCache.share, {"canonical":"default:vue@3.5.45","aliases":["vue@3.5.45"]});
    if (exportModule === undefined) {
      __mfSubscribeSharedCache(__mfModuleCache.share, {"canonical":"default:vue@3.5.45"}, (mod) => {
        exportModule = mod;
        __mfApplyHostProvidedExports(mod);
      });
      __mfTrackPendingShareLoad(initPromise.then(() => {
        exportModule = __mfReadSharedCache(__mfModuleCache.share, {"canonical":"default:vue@3.5.45","aliases":["vue@3.5.45"]});
        // A share init() left to its dynamic import is normally bridged before that import runs;
        // bridge it here when this wrapper is reached another way.
        if (exportModule === undefined && typeof __mfPromiseState.loadLazyShares === "function") {
          return __mfPromiseState.loadLazyShares(["vue"]).then(() => {
            exportModule = __mfReadSharedCache(__mfModuleCache.share, {"canonical":"default:vue@3.5.45","aliases":["vue@3.5.45"]});
          });
        }
      }).then(() => {
        if (exportModule === undefined) {
          throw new Error("[Module Federation] Shared module vue was imported before federation bootstrap finished.");
        }
        __mfApplyHostProvidedExports(exportModule);
      }));
    } else {
      __mfApplyHostProvidedExports(exportModule);
    }

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

export { _export_sfc as _, __mf_13 as a, __mf_2 as b, __mf_1 as c, __mf_15 as d, __mf_18 as e, __mf_16 as f, __mf_9 as g, __mf_12 as h, __mf_0 as i, __mf_19 as j, __mf_10 as k, __mf_11 as l, __mf_6 as m, __mf_14 as n, __mf_7 as o, __mf_5 as p, __mf_8 as q, __mf_4 as r, __mf_17 as s, __mf_3 as t };
