<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px">
        <span>客户互动</span>
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
              {{ row.productDetails?.productName || row.subjectName || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="评分" width="100" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.productValuation >= 4 ? '#67c23a' : row.productValuation >= 3 ? '#e6a23c' : '#f56c6c', fontWeight: 'bold' }">
                {{ '★'.repeat(row.productValuation) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="评价内容" min-width="300">
            <template #default="{ row }">
              <div v-if="row.textZh" style="font-size: 13px; margin-bottom: 4px">{{ row.textZh }}</div>
              <div :style="{ color: row.textZh ? '#999' : '', fontSize: row.textZh ? '12px' : '13px' }">{{ row.text || '-' }}</div>
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
              <el-button size="small" type="primary" @click="openReplyDialog(row, 'feedback')">
                {{ row.answer ? '查看' : '回复' }}
              </el-button>
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
              {{ row.productDetails?.productName || row.subjectName || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="问题内容" min-width="350">
            <template #default="{ row }">
              <div v-if="row.textZh" style="font-size: 13px; margin-bottom: 4px">{{ row.textZh }}</div>
              <div :style="{ color: row.textZh ? '#999' : '', fontSize: row.textZh ? '12px' : '13px' }">{{ row.text || '-' }}</div>
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

  <!-- 回复对话框 -->
  <el-dialog v-model="showReplyDialog" :title="replyType === 'feedback' ? '评价详情' : '问题详情'" width="600px">
    <div v-if="replyItem" style="margin-bottom: 16px">
      <p style="color: #666; margin-bottom: 8px"><strong>产品：</strong>{{ replyItem.productDetails?.productName || replyItem.subjectName || '-' }}</p>
      <p v-if="replyType === 'feedback'" style="margin-bottom: 8px">
        <strong>评分：</strong>
        <span :style="{ color: replyItem.productValuation >= 4 ? '#67c23a' : '#e6a23c' }">
          {{ '★'.repeat(replyItem.productValuation) }}{{ '☆'.repeat(5 - replyItem.productValuation) }}
        </span>
      </p>
      <p style="margin-bottom: 8px"><strong>{{ replyType === 'feedback' ? '评价' : '问题' }}：</strong></p>
      <div style="background: #f5f7fa; padding: 12px; border-radius: 4px; margin-bottom: 16px">
        <div v-if="replyItem.textZh" style="margin-bottom: 6px">{{ replyItem.textZh }}</div>
        <div :style="{ color: replyItem.textZh ? '#999' : '' }">{{ replyItem.text || '-' }}</div>
      </div>
      <div v-if="replyItem.answer">
        <p style="margin-bottom: 8px"><strong>已回复：</strong></p>
        <div style="background: #f0f9eb; padding: 12px; border-radius: 4px">
          <div v-if="replyItem.answer._textZh" style="margin-bottom: 6px">{{ replyItem.answer._textZh }}</div>
          <div :style="{ color: replyItem.answer._textZh ? '#999' : '' }">{{ replyItem.answer.text }}</div>
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
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

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
    if (data.length > 0) {
      shopId.value = data[0].id
      fetchData()
    }
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

onMounted(fetchShops)
</script>
