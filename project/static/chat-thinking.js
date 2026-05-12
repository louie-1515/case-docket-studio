/**
 * 聊天思考状态管理器
 *
 * 用途：在小扣聊天面板中管理“思考中→流式输出”的完整生命周期。
 * 风格：克制、专业，slate 色系，无渐变，纯 CSS 动画。
 *
 * 用法：
 *   const thinking = ChatThinking.start(messagesEl, {
 *       stages: ['检索相关证据', '模型正在分析']
 *   });
 *   // … API 调用 …
 *   thinking.transitionToStream(answerContent, '小扣 · 分析');
 *
 * 流式输出支持两种模式：
 *   1. simulate  — 前端逐字打字（默认，适配现有单次 API 响应）
 *   2. token     — 后端 SSE 推送 token（未来扩展，直接 appendToken）
 */
(function () {
    'use strict';

    const TICK_MS = 22;        // 逐字间隔
    const TIMEOUT_HINT_S = 20;  // 超过此秒数显示"请耐心等待"提示

    /**
     * @param {HTMLElement} container  — 消息列表容器 (.companion-messages)
     * @param {object}      [opts]
     * @param {string[]}    [opts.stages] — 阶段标签数组
     * @returns {object} 控制器 { setStage, advanceStage, startTimer, stopTimer, transitionToStream, appendToken, abort }
     */
    function ChatThinking(container, opts) {
        opts = opts || {};
        var stages = opts.stages || ['检索相关证据', '模型正在分析'];

        var _el = null;
        var _stagesEl = null;
        var _stageItems = [];     // { el, label }
        var _timerEl = null;
        var _labelEl = null;
        var _timerStart = 0;
        var _timerInterval = 0;
        var _activeStageIdx = 0;
        var _aborted = false;

        var _streamMsgEl = null;
        var _streamContentEl = null;
        var _streamCursorEl = null;

        /* ---------- 构建 DOM ---------- */

        function build() {
            _el = document.createElement('div');
            _el.className = 'think-bubble';

            // meta 行
            var meta = document.createElement('div');
            meta.className = 'think-meta';

            var spinner = document.createElement('span');
            spinner.className = 'think-spinner';
            meta.appendChild(spinner);

            _labelEl = document.createElement('span');
            _labelEl.className = 'think-label';
            _labelEl.textContent = '小扣正在处理';
            meta.appendChild(_labelEl);

            _timerEl = document.createElement('span');
            _timerEl.className = 'think-timer';
            _timerEl.textContent = '';
            meta.appendChild(_timerEl);

            _el.appendChild(meta);

            // stages
            _stagesEl = document.createElement('div');
            _stagesEl.className = 'think-stages';
            _el.appendChild(_stagesEl);

            // 初始只有 activeStageIdx 是 active，其余的 pending
            for (var i = 0; i < stages.length; i++) {
                var stageRow = _makeStageRow(stages[i], i === 0 ? 'is-active' : 'is-pending');
                _stagesEl.appendChild(stageRow.el);
                _stageItems.push(stageRow);
            }

            _activeStageIdx = 0;
            container.appendChild(_el);
            scrollToBottom(container);
        }

        function _makeStageRow(label, cls) {
            var row = document.createElement('div');
            row.className = 'think-stage ' + (cls || '');

            var icon = document.createElement('span');
            icon.className = 'stage-icon';

            var dot = document.createElement('span');
            dot.className = 'stage-dot';
            icon.appendChild(dot);

            var text = document.createElement('span');
            text.className = 'stage-text';
            text.textContent = label;

            row.appendChild(icon);
            row.appendChild(text);

            return { el: row, label: label, dot: dot, icon: icon };
        }

        /* ---------- 阶段控制 ---------- */

        /** 设置当前 active 阶段的标签文本 */
        function setStage(label) {
            if (_aborted) return;
            if (_stageItems[_activeStageIdx]) {
                _stageItems[_activeStageIdx].el.querySelector('.stage-text').textContent = label;
                _stageItems[_activeStageIdx].label = label;
            }
            if (_labelEl && _activeStageIdx < stages.length) {
                _labelEl.textContent = '小扣' + (label ? ' · ' + label : '正在处理');
            }
        }

        /**
         * 推进到下一阶段（标记当前为 done，激活下一项）
         * @param {string}  [detail]  — 附加到 done 阶段的详情（如结果数量）
         */
        function advanceStage(detail) {
            if (_aborted) return;
            if (_activeStageIdx >= stages.length - 1) return;

            // 标记当前为 done
            var cur = _stageItems[_activeStageIdx];
            if (cur) {
                cur.el.className = 'think-stage is-done';
                if (detail) {
                    cur.el.querySelector('.stage-text').textContent = cur.label + ' ' + detail;
                }
            }

            // 激活下一项
            _activeStageIdx++;
            var next = _stageItems[_activeStageIdx];
            if (next) {
                next.el.className = 'think-stage is-active';
                _labelEl.textContent = '小扣 · ' + next.label;
            }

            scrollToBottom(); // container kept in closure
        }

        /* ---------- 计时器 ---------- */

        function startTimer() {
            if (_timerStart) return;
            _timerStart = Date.now();
            _timerEl.textContent = '已等待 0 秒';
            _timerInterval = setInterval(_tick, 1000);
        }

        function stopTimer() {
            if (_timerInterval) clearInterval(_timerInterval);
            _timerInterval = 0;
        }

        function _tick() {
            if (_aborted) { stopTimer(); return; }
            var elapsed = Math.floor((Date.now() - _timerStart) / 1000);
            _timerEl.textContent = '已等待 ' + elapsed + ' 秒';

            // 超时提示
            if (elapsed >= TIMEOUT_HINT_S && !_el.querySelector('.think-timeout-hint')) {
                var hint = document.createElement('div');
                hint.className = 'think-timeout-hint';
                hint.textContent = '回答较长，请耐心等待';
                _el.appendChild(hint);
            }
        }

        /* ---------- 过渡到流式输出 ---------- */

        /**
         * 移除思考气泡，插入助手消息，开始逐字打字。
         * @param {string} content — 完整回复文本
         * @param {string} role    — 角色标签，如 '小扣 · 分析'
         * @param {object} [opts]
         * @param {number} [opts.speed] — 逐字间隔 ms，默认 22
         * @returns {Promise<void>} 打字完成后 resolve
         */
        function transitionToStream(content, role, opts) {
            if (_aborted) return Promise.resolve();
            opts = opts || {};
            var speed = opts.speed || TICK_MS;

            stopTimer();

            // 标记最后一个阶段为 done
            var cur = _stageItems[_activeStageIdx];
            if (cur) {
                cur.el.className = 'think-stage is-done';
            }

            // 淡出思考气泡
            _el.classList.add('is-exiting');

            // 同时插入流式消息
            _streamMsgEl = document.createElement('div');
            _streamMsgEl.className = 'chat-message is-assistant is-streaming';

            var roleDiv = document.createElement('div');
            roleDiv.className = 'chat-role';
            roleDiv.textContent = role || '小扣';
            _streamMsgEl.appendChild(roleDiv);

            _streamContentEl = document.createElement('div');
            _streamContentEl.className = 'chat-content streaming-content';
            _streamContentEl.textContent = '';
            _streamMsgEl.appendChild(_streamContentEl);

            _streamCursorEl = document.createElement('span');
            _streamCursorEl.className = 'streaming-cursor';
            _streamContentEl.appendChild(_streamCursorEl);

            // 在 think bubble 之后插入
            if (_el && _el.parentNode) {
                _el.parentNode.insertBefore(_streamMsgEl, _el.nextSibling);
            } else {
                container.appendChild(_streamMsgEl);
            }

            // 思考气泡淡出完成后移除
            setTimeout(function () {
                if (_el && _el.parentNode) {
                    _el.parentNode.removeChild(_el);
                    _el = null;
                }
            }, 200);

            return _typeContent(content, speed);
        }

        function _typeContent(content, speed) {
            var chars = content.split('');
            var idx = 0;
            var _streamDone = false;

            return new Promise(function (resolve) {
                function next() {
                    if (_aborted || idx >= chars.length) {
                        if (_streamCursorEl) {
                            _streamCursorEl.classList.add('is-done');
                        }
                        if (_streamMsgEl) {
                            _streamMsgEl.classList.remove('is-streaming');
                        }
                        _streamDone = true;
                        resolve();
                        return;
                    }
                    // 批量追加一组字符以获得更平滑的渲染
                    var batch = Math.max(1, Math.floor(speed > 10 ? 2 : 1));
                    var fragment = '';
                    for (var i = 0; i < batch && idx < chars.length; i++) {
                        fragment += chars[idx];
                        idx++;
                    }
                    _streamContentEl.insertBefore(
                        document.createTextNode(fragment),
                        _streamCursorEl
                    );
                    scrollToBottom();
                    setTimeout(next, speed);
                }
                next();
            });
        }

        /**
         * SSE 模式：先创建流式消息壳子（不开始打字），后续通过 appendToken 追加。
         * @param {string} role — 角色标签，如 '小扣 · 分析'
         */
        function beginStream(role) {
            if (_aborted) return;
            stopTimer();

            // 标记剩余所有阶段为 done
            for (var i = _activeStageIdx; i < _stageItems.length; i++) {
                _stageItems[i].el.className = 'think-stage is-done';
            }

            // 淡出思考气泡
            _el.classList.add('is-exiting');

            // 创建流式消息
            _streamMsgEl = document.createElement('div');
            _streamMsgEl.className = 'chat-message is-assistant is-streaming';

            var roleDiv = document.createElement('div');
            roleDiv.className = 'chat-role';
            roleDiv.textContent = role || '小扣';
            _streamMsgEl.appendChild(roleDiv);

            _streamContentEl = document.createElement('div');
            _streamContentEl.className = 'chat-content streaming-content';
            _streamContentEl.textContent = '';
            _streamMsgEl.appendChild(_streamContentEl);

            _streamCursorEl = document.createElement('span');
            _streamCursorEl.className = 'streaming-cursor';
            _streamContentEl.appendChild(_streamCursorEl);

            // 在 think bubble 之后插入
            if (_el && _el.parentNode) {
                _el.parentNode.insertBefore(_streamMsgEl, _el.nextSibling);
            } else {
                container.appendChild(_streamMsgEl);
            }

            // 思考气泡淡出完成后移除
            setTimeout(function () {
                if (_el && _el.parentNode) {
                    _el.parentNode.removeChild(_el);
                    _el = null;
                }
            }, 200);

            scrollToBottom();
        }

        /**
         * 外部追加 token（SSE 模式）。
         */
        function appendToken(text) {
            if (_aborted || !_streamContentEl || !_streamCursorEl) return;
            _streamContentEl.insertBefore(
                document.createTextNode(text),
                _streamCursorEl
            );
            scrollToBottom();
        }

        /**
         * 结束流式输出（标记完成）。
         */
        function finishStream() {
            if (_streamCursorEl) {
                _streamCursorEl.classList.add('is-done');
            }
            if (_streamMsgEl) {
                _streamMsgEl.classList.remove('is-streaming');
            }
        }

        /* ---------- 中止 ---------- */

        function abort() {
            _aborted = true;
            stopTimer();
            if (_el && _el.parentNode) {
                _el.parentNode.removeChild(_el);
                _el = null;
            }
            if (_streamMsgEl) {
                finishStream();
            }
        }

        /* ---------- 工具 ---------- */

        function scrollToBottom(ct) {
            ct = ct || container;
            if (ct) {
                ct.scrollTop = ct.scrollHeight;
            }
        }

        /* ---------- 初始化 ---------- */

        build();
        startTimer();

        return {
            setStage: setStage,
            advanceStage: advanceStage,
            startTimer: startTimer,
            stopTimer: stopTimer,
            transitionToStream: transitionToStream,
            beginStream: beginStream,
            appendToken: appendToken,
            finishStream: finishStream,
            abort: abort,
            /** 暴露 DOM 引用，方便高级用户 */
            getEl: function () { return _el; },
            getStreamEl: function () { return _streamMsgEl; },
            isAborted: function () { return _aborted; }
        };
    }

    /** 快捷工厂 */
    ChatThinking.start = function (container, opts) {
        return new ChatThinking(container, opts);
    };

    window.ChatThinking = ChatThinking;
})();
