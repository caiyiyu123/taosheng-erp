<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px">
        <span>评价客服</span>
        <div style="display: flex; gap: 8px; align-items: center">
          <el-select v-model="shopId" placeholder="选择店铺" size="small" style="width: 150px" @change="onFilterChange">
            <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
          <el-select v-if="activeTab !== 'chats'" v-model="isAnswered" size="small" style="width: 120px" @change="onFilterChange">
            <el-option label="未回复" :value="false" />
            <el-option label="已回复" :value="true" />
          </el-select>
        </div>
      </div>
    </template>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- 评价 Tab -->
      <el-tab-pane label="评价" name="feedbacks">
        <el-table :data="feedbacks" stripe v-loading="loading">
          <el-table-column label="图片" width="80">
            <template #default="{ row }">
              <el-image v-if="row._imageUrl" :src="row._imageUrl" style="width: 50px; height: 65px" fit="cover" lazy />
              <span v-else style="color: #ccc">无图</span>
            </template>
          </el-table-column>
          <el-table-column label="产品" min-width="200">
            <template #default="{ row }">
              <a v-if="row.productDetails?.nmId" :href="'https://www.wildberries.ru/catalog/' + row.productDetails.nmId + '/detail.aspx'" target="_blank" style="color: #409eff; text-decoration: none; cursor: pointer">
                {{ row.productDetails?.productName || row.subjectName || '-' }}
              </a>
              <span v-else>{{ row.subjectName || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="评分" width="100" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.productValuation >= 4 ? '#67c23a' : row.productValuation >= 3 ? '#e6a23c' : '#f56c6c', fontWeight: 'bold' }">
                {{ '★'.repeat(row.productValuation) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="评价内容" min-width="400">
            <template #default="{ row }">
              <div v-if="row.pros" style="font-size: 13px; margin-bottom: 4px"><span style="color: #67c23a; font-weight: 500">优点：</span>{{ row.pros }}</div>
              <div v-if="row.cons" style="font-size: 13px; margin-bottom: 4px"><span style="color: #f56c6c; font-weight: 500">缺点：</span>{{ row.cons }}</div>
              <div v-if="row.text" style="font-size: 13px"><span style="color: #909399; font-weight: 500">评论：</span>{{ row.text }}</div>
              <div v-if="!row.pros && !row.cons && !row.text" style="color: #ccc">-</div>
              <div v-if="row.photoLinks && row.photoLinks.length" style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px">
                <el-image v-for="(p, i) in row.photoLinks" :key="i" :src="p.miniSize || p.fullSize" :preview-src-list="row.photoLinks.map(x => x.fullSize || x.miniSize)" preview-teleported style="width: 40px; height: 40px; border-radius: 4px" fit="cover" />
              </div>
              <div v-if="row.video && row.video.url" style="margin-top: 6px">
                <a :href="row.video.url" target="_blank" style="color: #409eff; font-size: 12px; text-decoration: none">查看视频</a>
              </div>
              <div v-if="row._allZh" style="color: #409eff; font-size: 12px; margin-top: 4px; white-space: pre-line">{{ row._allZh }}</div>
              <el-button v-else-if="row.pros || row.cons || row.text" link type="primary" size="small" style="margin-top: 2px; font-size: 12px" :loading="row._translating" @click="translateFeedback(row)">翻译</el-button>
            </template>
          </el-table-column>
          <el-table-column label="日期" width="110" align="center">
            <template #default="{ row }">{{ formatDate(row.createdDate) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.answer" type="success" size="small">已回复</el-tag>
              <el-tag v-else type="warning" size="small">待回复</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="openReplyDialog(row, 'feedback')">
                {{ row.answer ? '查看' : '回复' }}
              </el-button>
              <el-dropdown v-if="!row.answer && replyTemplates.length" trigger="click" @command="cmd => quickReply(row, cmd, 'feedback')" style="margin-top: 4px">
                <el-button size="small" :loading="row._quickReplying">一键回复</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-for="t in replyTemplates" :key="t.id" :command="t.content">{{ t.name }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 问题 Tab -->
      <el-tab-pane label="问题" name="questions">
        <el-table :data="questions" stripe v-loading="loading">
          <el-table-column label="图片" width="80">
            <template #default="{ row }">
              <el-image v-if="row._imageUrl" :src="row._imageUrl" style="width: 50px; height: 65px" fit="cover" lazy />
              <span v-else style="color: #ccc">无图</span>
            </template>
          </el-table-column>
          <el-table-column label="产品" min-width="200">
            <template #default="{ row }">
              <a v-if="row.productDetails?.nmId" :href="'https://www.wildberries.ru/catalog/' + row.productDetails.nmId + '/detail.aspx'" target="_blank" style="color: #409eff; text-decoration: none; cursor: pointer">
                {{ row.productDetails?.productName || row.subjectName || '-' }}
              </a>
              <span v-else>{{ row.subjectName || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="问题内容" min-width="350">
            <template #default="{ row }">
              <div style="font-size: 13px">{{ row.text || '-' }}</div>
              <div v-if="row._textZh" style="color: #409eff; font-size: 12px; margin-top: 4px">{{ row._textZh }}</div>
              <el-button v-else-if="row.text" link type="primary" size="small" style="margin-top: 2px; font-size: 12px" :loading="row._translating" @click="translateRow(row)">翻译</el-button>
            </template>
          </el-table-column>
          <el-table-column label="日期" width="110" align="center">
            <template #default="{ row }">{{ formatDate(row.createdDate) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.answer" type="success" size="small">已回复</el-tag>
              <el-tag v-else type="warning" size="small">待回复</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="openReplyDialog(row, 'question')">
                {{ row.answer ? '查看' : '回复' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 评价模板 Tab -->
      <el-tab-pane label="评价模板" name="templates">
        <div style="display: flex; justify-content: flex-end; margin-bottom: 12px">
          <el-button type="primary" size="small" @click="openTemplateDialog()">添加模板</el-button>
        </div>
        <el-table :data="replyTemplates" stripe>
          <el-table-column prop="name" label="模板名称" width="200" />
          <el-table-column prop="content" label="回复内容" min-width="400" />
          <el-table-column label="操作" width="140" align="center">
            <template #default="{ row }">
              <el-button size="small" link @click="openTemplateDialog(row)">编辑</el-button>
              <el-popconfirm title="确定删除该模板?" @confirm="deleteReplyTemplate(row.id)">
                <template #reference>
                  <el-button size="small" link type="danger">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 聊天 Tab -->
      <el-tab-pane label="聊天" name="chats">
        <div style="display: flex; height: 500px; border: 1px solid #e4e7ed; border-radius: 4px">
          <!-- 聊天列表 -->
          <div style="width: 280px; border-right: 1px solid #e4e7ed; overflow-y: auto">
            <div v-if="loading" style="padding: 20px; text-align: center; color: #999">加载中...</div>
            <div v-else-if="chatList.length === 0" style="padding: 20px; text-align: center; color: #999">暂无聊天</div>
            <div
              v-for="chat in chatList" :key="chat.chatId || chat.id"
              @click="selectChat(chat)"
              :style="{
                padding: '12px 16px', cursor: 'pointer', borderBottom: '1px solid #f0f0f0',
                background: selectedChat && (selectedChat.chatId || selectedChat.id) === (chat.chatId || chat.id) ? '#f0f7ff' : ''
              }"
            >
              <div style="font-weight: 500; font-size: 14px">{{ chat.userName || chat.buyerName || '买家' }}</div>
              <div style="color: #999; font-size: 12px; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
                {{ chat.lastMessage || '' }}
              </div>
            </div>
          </div>
          <!-- 消息区域 -->
          <div style="flex: 1; display: flex; flex-direction: column">
            <div v-if="!selectedChat" style="flex: 1; display: flex; align-items: center; justify-content: center; color: #999">
              选择一个聊天
            </div>
            <template v-else>
              <div ref="messagesContainer" style="flex: 1; overflow-y: auto; padding: 16px">
                <div v-for="(msg, i) in chatMessages" :key="i" :style="{ textAlign: msg.isSeller ? 'right' : 'left', marginBottom: '12px' }">
                  <div :style="{
                    display: 'inline-block', padding: '8px 12px', borderRadius: '8px', maxWidth: '70%', textAlign: 'left',
                    background: msg.isSeller ? '#409eff' : '#f4f4f5',
                    color: msg.isSeller ? '#fff' : '#333'
                  }">
                    {{ msg.text || msg.message || '' }}
                  </div>
                  <div style="font-size: 11px; color: #bbb; margin-top: 2px">{{ formatDate(msg.createdAt || msg.dt) }}</div>
                </div>
              </div>
              <div style="padding: 12px; border-top: 1px solid #e4e7ed; display: flex; gap: 8px">
                <el-input v-model="chatInput" placeholder="输入消息..." @keyup.enter="sendMessage" />
                <el-button type="primary" @click="sendMessage" :loading="sending">发送</el-button>
              </div>
            </template>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-card>

  <!-- 模板编辑对话框 -->
  <el-dialog v-model="showTemplateDialog" :title="templateForm.id ? '编辑模板' : '添加模板'" width="500px">
    <el-form :model="templateForm" label-width="80px">
      <el-form-item label="模板名称">
        <el-input v-model="templateForm.name" placeholder="如：好评感谢" />
      </el-form-item>
      <el-form-item label="回复内容">
        <el-input v-model="templateForm.content" type="textarea" :rows="5" placeholder="输入回复模板内容..." />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showTemplateDialog = false">取消</el-button>
      <el-button type="primary" @click="saveReplyTemplate">保存</el-button>
    </template>
  </el-dialog>

  <!-- 回复对话框 -->
  <el-dialog v-model="showReplyDialog" :title="replyType === 'feedback' ? '评价详情' : '问题详情'" width="600px">
    <div v-if="replyItem" style="margin-bottom: 16px">
      <p style="color: #666; margin-bottom: 8px">
        <strong>产品：</strong>
        <a v-if="replyItem.productDetails?.nmId" :href="'https://www.wildberries.ru/catalog/' + replyItem.productDetails.nmId + '/detail.aspx'" target="_blank" style="color: #409eff; text-decoration: none">
          {{ replyItem.productDetails?.productName || replyItem.subjectName || '-' }}
        </a>
        <span v-else>{{ replyItem.subjectName || '-' }}</span>
      </p>
      <p v-if="replyType === 'feedback'" style="margin-bottom: 8px">
        <strong>评分：</strong>
        <span :style="{ color: replyItem.productValuation >= 4 ? '#67c23a' : '#e6a23c' }">
          {{ '★'.repeat(replyItem.productValuation) }}{{ '☆'.repeat(5 - replyItem.productValuation) }}
        </span>
      </p>
      <p style="margin-bottom: 8px"><strong>{{ replyType === 'feedback' ? '评价' : '问题' }}：</strong></p>
      <div style="background: #f5f7fa; padding: 12px; border-radius: 4px; margin-bottom: 16px">
        <template v-if="replyType === 'feedback'">
          <div v-if="replyItem.pros" style="margin-bottom: 6px"><span style="color: #67c23a; font-weight: 500">优点：</span>{{ replyItem.pros }}</div>
          <div v-if="replyItem.cons" style="margin-bottom: 6px"><span style="color: #f56c6c; font-weight: 500">缺点：</span>{{ replyItem.cons }}</div>
          <div v-if="replyItem.text"><span style="color: #909399; font-weight: 500">评论：</span>{{ replyItem.text }}</div>
          <div v-if="!replyItem.pros && !replyItem.cons && !replyItem.text">-</div>
          <div v-if="replyItem.photoLinks && replyItem.photoLinks.length" style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px">
            <el-image v-for="(p, i) in replyItem.photoLinks" :key="i" :src="p.fullSize || p.miniSize" :preview-src-list="replyItem.photoLinks.map(x => x.fullSize || x.miniSize)" preview-teleported style="width: 80px; height: 80px; border-radius: 6px" fit="cover" />
          </div>
          <div v-if="replyItem.video && replyItem.video.url" style="margin-top: 10px">
            <video :src="replyItem.video.url" controls style="max-width: 100%; max-height: 240px; border-radius: 6px"></video>
          </div>
          <div v-if="replyItem._allZh" style="color: #409eff; margin-top: 6px; white-space: pre-line">{{ replyItem._allZh }}</div>
          <el-button v-else-if="replyItem.pros || replyItem.cons || replyItem.text" link type="primary" size="small" style="margin-top: 4px" :loading="replyItem._translating" @click="translateFeedback(replyItem)">翻译</el-button>
        </template>
        <template v-else>
          <div>{{ replyItem.text || '-' }}</div>
          <div v-if="replyItem._textZh" style="color: #409eff; margin-top: 6px">{{ replyItem._textZh }}</div>
          <el-button v-else-if="replyItem.text" link type="primary" size="small" style="margin-top: 4px" :loading="replyItem._translating" @click="translateRow(replyItem)">翻译</el-button>
        </template>
      </div>
      <div v-if="replyItem.answer">
        <p style="margin-bottom: 8px"><strong>已回复：</strong></p>
        <div style="background: #f0f9eb; padding: 12px; border-radius: 4px">
          <div>{{ replyItem.answer.text }}</div>
          <div v-if="replyItem.answer._textZh" style="color: #409eff; margin-top: 6px">{{ replyItem.answer._textZh }}</div>
          <el-button v-else-if="replyItem.answer.text" link type="primary" size="small" style="margin-top: 4px" :loading="replyItem.answer._translating" @click="translateAnswer(replyItem.answer)">翻译</el-button>
        </div>
      </div>
      <div v-else>
        <p style="margin-bottom: 8px"><strong>回复：</strong></p>
        <el-input v-model="replyText" type="textarea" :rows="4" placeholder="输入回复内容..." />
      </div>
    </div>
    <template #footer>
      <el-button @click="showReplyDialog = false">关闭</el-button>
      <el-button v-if="replyItem && !replyItem.answer" type="primary" @click="submitReply" :loading="sending">提交回复</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

// ==================== 评价模板 ====================
const TEMPLATE_KEY = 'erp_reply_templates'
const replyTemplates = ref([])
const showTemplateDialog = ref(false)
const templateForm = reactive({ id: null, name: '', content: '' })

function loadTemplates() {
  try {
    replyTemplates.value = JSON.parse(localStorage.getItem(TEMPLATE_KEY) || '[]')
  } catch { replyTemplates.value = [] }
}

function saveTemplates() {
  localStorage.setItem(TEMPLATE_KEY, JSON.stringify(replyTemplates.value))
}

function openTemplateDialog(row) {
  if (row) {
    templateForm.id = row.id
    templateForm.name = row.name
    templateForm.content = row.content
  } else {
    templateForm.id = null
    templateForm.name = ''
    templateForm.content = ''
  }
  showTemplateDialog.value = true
}

function saveReplyTemplate() {
  if (!templateForm.name.trim() || !templateForm.content.trim()) {
    ElMessage.warning('请填写模板名称和内容')
    return
  }
  if (templateForm.id) {
    const t = replyTemplates.value.find(x => x.id === templateForm.id)
    if (t) { t.name = templateForm.name; t.content = templateForm.content }
  } else {
    replyTemplates.value.push({ id: Date.now(), name: templateForm.name, content: templateForm.content })
  }
  saveTemplates()
  showTemplateDialog.value = false
  ElMessage.success('保存成功')
}

function deleteReplyTemplate(id) {
  replyTemplates.value = replyTemplates.value.filter(x => x.id !== id)
  saveTemplates()
  ElMessage.success('删除成功')
}

async function quickReply(row, text, type) {
  if (!shopId.value) { ElMessage.warning('请先选择店铺'); return }
  row._quickReplying = true
  try {
    const endpoint = type === 'feedback' ? '/api/customer-service/feedbacks/reply' : '/api/customer-service/questions/reply'
    await api.post(endpoint, { shop_id: shopId.value, id: row.id, text })
    ElMessage.success('回复成功')
    fetchData()
  } catch (e) {
    ElMessage.error('回复失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    row._quickReplying = false
  }
}

const shops = ref([])
const shopId = ref(null)
const isAnswered = ref(false)
const activeTab = ref('feedbacks')
const loading = ref(false)
const sending = ref(false)

// Feedbacks
const feedbacks = ref([])
// Questions
const questions = ref([])
// Chats
const chatList = ref([])
const selectedChat = ref(null)
const chatMessages = ref([])
const chatInput = ref('')
const messagesContainer = ref(null)

// Reply dialog
const showReplyDialog = ref(false)
const replyItem = ref(null)
const replyType = ref('')
const replyText = ref('')

function formatDate(dt) {
  if (!dt) return '-'
  try {
    return new Date(dt).toLocaleDateString('zh-CN')
  } catch { return dt }
}

async function fetchShops() {
  try {
    const { data } = await api.get('/api/shops')
    shops.value = data
  } catch {}
}

function onFilterChange() {
  if (shopId.value) fetchData()
}

function onTabChange() {
  if (shopId.value) fetchData()
}

async function fetchData() {
  if (!shopId.value) return
  loading.value = true
  try {
    if (activeTab.value === 'feedbacks') {
      const { data } = await api.get('/api/customer-service/feedbacks', {
        params: { shop_id: shopId.value, is_answered: isAnswered.value, take: 50 }
      })
      feedbacks.value = data?.data?.feedbacks || []
    } else if (activeTab.value === 'questions') {
      const { data } = await api.get('/api/customer-service/questions', {
        params: { shop_id: shopId.value, is_answered: isAnswered.value, take: 50 }
      })
      questions.value = data?.data?.questions || []
    } else if (activeTab.value === 'chats') {
      const { data } = await api.get('/api/customer-service/chats', {
        params: { shop_id: shopId.value }
      })
      chatList.value = Array.isArray(data) ? data : []
      selectedChat.value = null
      chatMessages.value = []
    }
  } catch (e) {
    ElMessage.error('数据加载失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

async function selectChat(chat) {
  selectedChat.value = chat
  const chatId = chat.chatId || chat.id
  try {
    const { data } = await api.get(`/api/customer-service/chats/${chatId}/messages`, {
      params: { shop_id: shopId.value }
    })
    chatMessages.value = Array.isArray(data) ? data : []
    await nextTick()
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  } catch (e) {
    ElMessage.error('加载消息失败')
  }
}

async function sendMessage() {
  if (!chatInput.value.trim() || !selectedChat.value) return
  const chatId = selectedChat.value.chatId || selectedChat.value.id
  sending.value = true
  try {
    await api.post(`/api/customer-service/chats/${chatId}/message`, {
      shop_id: shopId.value, text: chatInput.value
    })
    chatInput.value = ''
    ElMessage.success('发送成功')
    await selectChat(selectedChat.value)
  } catch (e) {
    ElMessage.error('发送失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    sending.value = false
  }
}

async function translateRow(row) {
  if (!row.text || row._textZh) return
  row._translating = true
  try {
    const { data } = await api.post('/api/customer-service/translate', { text: row.text })
    row._textZh = data.translated || ''
  } catch {
    ElMessage.error('翻译失败')
  } finally {
    row._translating = false
  }
}

async function translateFeedback(row) {
  if (row._allZh) return
  row._translating = true
  try {
    const parts = []
    if (row.pros) parts.push('优点：' + row.pros)
    if (row.cons) parts.push('缺点：' + row.cons)
    if (row.text) parts.push('评论：' + row.text)
    const fullText = [row.pros, row.cons, row.text].filter(Boolean).join('\n')
    const { data } = await api.post('/api/customer-service/translate', { text: fullText })
    row._allZh = data.translated || ''
  } catch {
    ElMessage.error('翻译失败')
  } finally {
    row._translating = false
  }
}

async function translateAnswer(answer) {
  if (!answer.text || answer._textZh) return
  answer._translating = true
  try {
    const { data } = await api.post('/api/customer-service/translate', { text: answer.text })
    answer._textZh = data.translated || ''
  } catch {
    ElMessage.error('翻译失败')
  } finally {
    answer._translating = false
  }
}

function openReplyDialog(item, type) {
  replyItem.value = item
  replyType.value = type
  replyText.value = ''
  showReplyDialog.value = true
}

async function submitReply() {
  if (!replyText.value.trim()) {
    ElMessage.warning('请输入回复内容')
    return
  }
  sending.value = true
  try {
    const endpoint = replyType.value === 'feedback' ? '/api/customer-service/feedbacks/reply' : '/api/customer-service/questions/reply'
    await api.post(endpoint, {
      shop_id: shopId.value,
      id: replyItem.value.id,
      text: replyText.value,
    })
    ElMessage.success('回复成功')
    showReplyDialog.value = false
    fetchData()
  } catch (e) {
    ElMessage.error('回复失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    sending.value = false
  }
}

onMounted(() => {
  fetchShops()
  loadTemplates()
})
</script>
