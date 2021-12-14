/*
 * -*- coding: utf-8 -*-
 * vim: ts=4 sw=4 tw=100 et ai si
 *
 * Copyright (C) 2019-2021 Intel, Inc.
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Author: Adam Hawley <adam.james.hawley@intel.com>
 */

import {LitElement, html, css} from 'lit';

import './diagram-element.js';
import './wult-metric-smry-tbl';

class WultMetricTab extends LitElement {
    static styles = css`
        .grid {
            display: grid;
            width: 100%;
            grid-auto-rows: 800px;
            grid-auto-flow: dense;
        }
  `;

    static properties = {
        tabname: {type: String},
        info: {type: Object},
        visible: {type: Boolean, attribute: false}
    };

    checkVisible() {
        let tab = document.getElementById(this.tabname);
        this.visible = tab.classList.contains('active');
    }

    connectedCallback(){
        super.connectedCallback();
        window.addEventListener("click", this._handleClick);
        this.checkVisible();
        this.paths = this.info.ppaths;
        this.smrystbl = this.info.smrys_tbl;
    }

    disconnectedCallback(){
        window.removeEventListener('click', this._handleClick);
        super.disconnectedCallback();
    }

    constructor() {
        super();
        this._handleClick = this.checkVisible.bind(this);
    }

    /*
     * Provides the template for when the tab is visible (active).
     */
    visibleTemplate() {
        return html`
            <wult-metric-smry-tbl .smrystbl="${this.smrystbl}"></wult-metric-smry-tbl>
            <div class="grid">
            ${this.paths.map((path) =>
                    html`<diagram-element path="${path}" ></diagram-element>`
            )}
            </div>
        `
    }

    render() {
        return this.visible
        ? html`${this.visibleTemplate()}`
        : html``;
    }
}

customElements.define('wult-metric-tab', WultMetricTab);