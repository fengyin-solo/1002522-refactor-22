<template>
  <section class="page" data-module="tool">
    <header class="page-head">
      <div>
        <h2>检修工具管理</h2>
        <p class="page-desc">维护检修工具，围绕工具编号、工具名称、规格型号、检定日期做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检修工具</button>
        <button class="btn" type="button" @click="exportRows">导出检修工具清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ formatCell(row[column]) }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无检修工具数据，可先登记检修工具</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条检修工具记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, unknown>

const ENDPOINT = '/api/tool'
const columns = [
  "工具编号",
  "工具名称",
  "规格型号",
  "检定日期",
  "下次检定日",
  "存放位置",
  "领用人",
  "报废日期",
  "工具状态",
]
const actions = ["办理领用", "送检测试", "申请报废"]
const statDefinitions = [
  { label: "合格工具", status: "合格可用" },
  { label: "待检定工具", status: "待检定" },
  { label: "已过期工具", status: "已过期" },
  { label: "已报废工具", status: "已报废" },
]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = computed(() => statDefinitions.map((item) => ({
  label: item.label,
  value: rows.value.filter((row) => row['工具状态'] === item.status).length,
})))
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function formatCell(value: unknown): string {
  if (Array.isArray(value)) {
    return value.length ? value.length + ' 条' : '—'
  }
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '检修工具登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await response.json()
    if (!response.ok || result.ok === false) {
      throw new Error(result.message || '检修工具动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检修工具操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('检修工具列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检修工具列表读取失败'
  }
}

onMounted(reload)
</script>
