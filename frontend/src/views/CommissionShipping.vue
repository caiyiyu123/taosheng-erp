<template>
  <el-card>
    <el-tabs v-model="mainTab">
      <!-- ====== 平台佣金 Tab ====== -->
      <el-tab-pane label="平台佣金" name="commission">
        <el-tabs v-model="platformTab" type="card" style="margin-bottom: 16px">
          <el-tab-pane label="WB本土" name="wb_local" />
          <el-tab-pane label="WB跨境" name="wb_cross_border" />
          <el-tab-pane label="OZON本土" name="ozon_local" />
        </el-tabs>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
          <div style="display: flex; align-items: center; gap: 12px">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".xlsx,.xls"
              :on-change="onFileSelected"
            >
              <el-button type="primary">上传佣金表格</el-button>
            </el-upload>
            <span v-if="commissionInfo.filename" style="color: #909399; font-size: 13px">
              当前文件：{{ commissionInfo.filename }}（{{ commissionInfo.uploaded_at }}）
            </span>
          </div>
          <div style="display: flex; gap: 8px">
            <el-input
              v-model="searchCategory"
              placeholder="搜索类目"
              clearable
              style="width: 180px"
              @input="onSearchInput"
            />
            <el-input
              v-model="searchProduct"
              placeholder="搜索商品名"
              clearable
              style="width: 180px"
              @input="onSearchInput"
            />
          </div>
        </div>

        <el-table :data="commissionRates" stripe max-height="600" v-loading="loadingRates">
          <el-table-column prop="category" label="类目" min-width="180" />
          <el-table-column prop="product_name" label="商品名称" min-width="180" />
          <el-table-column
            v-if="platformTab !== 'ozon_local'"
            label="佣金率"
            width="120"
            align="center"
          >
            <template #default="{ row }">{{ fmtRate(row.rate) }}</template>
          </el-table-column>
          <el-table-column
            v-for="h in extraHeaders"
            :key="h"
            :label="h"
            width="140"
            align="center"
          >
            <template #default="{ row }">{{ fmtRate(row[h]) }}</template>
          </el-table-column>
        </el-table>
        <div style="display: flex; justify-content: flex-end; margin-top: 12px">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="totalRates"
            :page-sizes="[50, 100, 200]"
            layout="total, sizes, prev, pager, next"
            @current-change="fetchCommissionRates"
            @size-change="onPageSizeChange"
          />
        </div>
      </el-tab-pane>

      <!-- ====== 头程运费 Tab ====== -->
      <el-tab-pane label="头程运费" name="shipping">
        <div style="display: flex; justify-content: flex-end; margin-bottom: 16px">
          <el-button type="primary" @click="openShippingDialog()">新增运费模板</el-button>
        </div>

        <div v-loading="loadingTemplates" style="display: flex; flex-wrap: wrap; gap: 12px">
          <div v-for="tpl in shippingTemplates" :key="tpl.id" style="flex: 0 0 calc(33.333% - 8px); min-width: 280px">
            <el-card shadow="hover" class="shipping-card">
              <template #header>
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0">
                  <div>
                    <span style="font-weight: 600; font-size: 15px">{{ tpl.name }}</span>
                    <span style="color: #909399; font-size: 13px; margin-left: 8px">{{ tpl.date }}</span>
                  </div>
                  <div style="display: flex; gap: 4px">
                    <el-button size="small" link @click="copyTemplate(tpl)">复制</el-button>
                    <el-button size="small" link @click="openShippingDialog(tpl)">编辑</el-button>
                    <el-popconfirm title="确定删除该模板?" @confirm="deleteTemplate(tpl.id)">
                      <template #reference>
                        <el-button size="small" link type="danger">删除</el-button>
                      </template>
                    </el-popconfirm>
                  </div>
                </div>
              </template>
              <el-table :data="tpl.rates" size="small" class="shipping-table">
                <el-table-column prop="density_min" label="密度下限" align="center" />
                <el-table-column prop="density_max" label="密度上限" align="center" />
                <el-table-column label="运费(USD)" align="center">
                  <template #default="{ row }"><span style="font-weight: 600">{{ row.price_usd }}</span></template>
                </el-table-column>
              </el-table>
            </el-card>
          </div>
          <el-empty v-if="!loadingTemplates && shippingTemplates.length === 0" description="暂无运费模板" style="width: 100%" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-card>

  <!-- 运费模板编辑对话框 -->
  <el-dialog v-model="showShippingDialog" :title="shippingForm.id ? '编辑运费模板' : '新增运费模板'" width="600px">
    <el-form :model="shippingForm" label-width="80px">
      <el-form-item label="头程名称">
        <el-input v-model="shippingForm.name" placeholder="如：空运-莫斯科" />
      </el-form-item>
      <el-form-item label="日期">
        <el-date-picker v-model="shippingForm.date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
      </el-form-item>
      <el-form-item label="密度区间">
        <div style="width: 100%">
          <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px; font-weight: 500; color: #606266; font-size: 13px">
            <span style="width: 130px; text-align: center">密度下限</span>
            <span style="width: 12px"></span>
            <span style="width: 130px; text-align: center">密度上限</span>
            <span style="width: 140px; text-align: center">运费 (USD)</span>
            <span style="width: 32px"></span>
          </div>
          <div
            v-for="(r, idx) in shippingForm.rates"
            :key="idx"
            style="display: flex; gap: 8px; align-items: center; margin-bottom: 4px"
          >
            <el-input-number v-model="r.density_min" :min="0" :precision="0" controls-position="right" style="width: 130px" />
            <span>~</span>
            <el-input-number v-model="r.density_max" :min="0" :precision="0" controls-position="right" style="width: 130px" />
            <el-input-number v-model="r.price_usd" :min="0" :precision="1" controls-position="right" style="width: 140px" />
            <el-button :icon="Delete" circle size="small" @click="shippingForm.rates.splice(idx, 1)" />
          </div>
          <el-button type="primary" link @click="shippingForm.rates.push({ density_min: 0, density_max: 0, price_usd: 0 })">
            + 添加行
          </el-button>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showShippingDialog = false">取消</el-button>
      <el-button type="primary" @click="saveTemplate">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import api from '../api'

function fmtRate(val) {
  if (val == null || val === 0) return ''
  return (val * 100).toFixed(2).replace(/\.?0+$/, '') + '%'
}

// ==================== 佣金部分 ====================
const mainTab = ref('commission')
const platformTab = ref('wb_local')
const searchCategory = ref('')
const searchProduct = ref('')
const commissionRates = ref([])
const extraHeaders = ref([])
const commissionInfo = reactive({ filename: null, uploaded_at: null })
const loadingRates = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const totalRates = ref(0)
let searchTimer = null

async function fetchCommissionRates() {
  loadingRates.value = true
  try {
    const { data } = await api.get('/api/commission/rates', {
      params: { platform: platformTab.value, category: searchCategory.value, product: searchProduct.value, page: currentPage.value, page_size: pageSize.value }
    })
    commissionRates.value = data.rates || []
    extraHeaders.value = data.headers || []
    totalRates.value = data.total || 0
  } catch { /* 无数据时静默 */ }
  finally { loadingRates.value = false }
}

function onPageSizeChange() {
  currentPage.value = 1
  fetchCommissionRates()
}

async function fetchCommissionInfo() {
  try {
    const { data } = await api.get('/api/commission/info', { params: { platform: platformTab.value } })
    commissionInfo.filename = data.filename
    commissionInfo.uploaded_at = data.uploaded_at ? new Date(data.uploaded_at).toLocaleString('zh-CN') : null
  } catch { /* ignore */ }
}

function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    currentPage.value = 1
    fetchCommissionRates()
  }, 400)
}

async function onFileSelected(file) {
  const formData = new FormData()
  formData.append('file', file.raw)
  try {
    loadingRates.value = true
    const { data } = await api.post(`/api/commission/upload?platform=${platformTab.value}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success(`上传成功，共 ${data.count} 条数据`)
    fetchCommissionRates()
    fetchCommissionInfo()
  } catch (e) {
    ElMessage.error('上传失败: ' + (e.response?.data?.detail || e.message))
  } finally { loadingRates.value = false }
}

watch(platformTab, () => {
  searchCategory.value = ''
  searchProduct.value = ''
  currentPage.value = 1
  fetchCommissionRates()
  fetchCommissionInfo()
})

// ==================== 运费模板部分 ====================
const shippingTemplates = ref([])
const loadingTemplates = ref(false)
const showShippingDialog = ref(false)
const shippingForm = reactive({ id: null, name: '', date: '', rates: [] })

async function fetchShippingTemplates() {
  loadingTemplates.value = true
  try {
    const { data } = await api.get('/api/shipping/templates')
    shippingTemplates.value = data
  } catch { /* 无数据时静默 */ }
  finally { loadingTemplates.value = false }
}

function openShippingDialog(row) {
  if (row) {
    shippingForm.id = row.id
    shippingForm.name = row.name
    shippingForm.date = row.date
    shippingForm.rates = row.rates.map(r => ({ ...r }))
  } else {
    shippingForm.id = null
    shippingForm.name = ''
    shippingForm.date = ''
    shippingForm.rates = Array.from({ length: 20 }, () => ({ density_min: 0, density_max: 0, price_usd: 0 }))
  }
  showShippingDialog.value = true
}

async function saveTemplate() {
  if (!shippingForm.name || !shippingForm.date) {
    ElMessage.warning('请填写名称和日期')
    return
  }
  const payload = { name: shippingForm.name, date: shippingForm.date, rates: shippingForm.rates }
  try {
    if (shippingForm.id) {
      await api.put(`/api/shipping/templates/${shippingForm.id}`, payload)
    } else {
      await api.post('/api/shipping/templates', payload)
    }
    showShippingDialog.value = false
    fetchShippingTemplates()
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

function copyTemplate(tpl) {
  shippingForm.id = null
  shippingForm.name = tpl.name + ' (副本)'
  shippingForm.date = tpl.date
  shippingForm.rates = tpl.rates.map(r => ({ ...r }))
  showShippingDialog.value = true
}

async function deleteTemplate(id) {
  try {
    await api.delete(`/api/shipping/templates/${id}`)
    fetchShippingTemplates()
    ElMessage.success('删除成功')
  } catch { ElMessage.error('删除失败') }
}

onMounted(() => {
  fetchCommissionRates()
  fetchCommissionInfo()
  fetchShippingTemplates()
})
</script>

<style scoped>
.shipping-card :deep(.el-card__header) {
  padding: 10px 14px;
}
.shipping-card :deep(.el-card__body) {
  padding: 0;
}
.shipping-table :deep(.el-table__cell) {
  padding: 4px 0;
  font-size: 14px;
}
</style>
