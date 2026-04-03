<template>
  <div class="ts-login">
    <div class="ts-login-bg"></div>
    <div class="ts-login-card">
      <div class="ts-login-header">
        <div class="ts-login-logo">
          <img src="/logo.png" alt="TS" class="ts-login-logo-icon" />
        </div>
        <h1 class="ts-login-title">{{ appTitle }}</h1>
        <p class="ts-login-subtitle">企业资源管理平台</p>
      </div>
      <el-form :model="form" @submit.prevent="handleLogin" class="ts-login-form">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" size="large" prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" size="large" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="loading" size="large" class="ts-login-btn">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'
import { APP_TITLE } from '../brand'

const appTitle = APP_TITLE

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const router = useRouter()
const authStore = useAuthStore()

async function handleLogin() {
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    router.push('/')
  } catch {
    ElMessage.error('用户名或密码错误')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.ts-login {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: #0f172a;
  position: relative;
  overflow: hidden;
}
.ts-login-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 20% 50%, rgba(245, 158, 11, 0.06) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 20%, rgba(20, 184, 166, 0.05) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 100%, rgba(59, 130, 246, 0.04) 0%, transparent 40%);
}
.ts-login-card {
  position: relative;
  width: 400px;
  background: rgba(15, 23, 42, 0.72);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: var(--ts-radius-lg);
  padding: 40px 36px 32px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
  animation: ts-fade-in 0.5s ease both;
}
.ts-login-header {
  text-align: center;
  margin-bottom: 36px;
}
.ts-login-logo {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}
.ts-login-logo-icon {
  width: 64px;
  height: 64px;
  object-fit: contain;
}
.ts-login-title {
  font-family: var(--ts-font);
  font-size: 28px;
  font-weight: 800;
  color: #f8fafc;
  margin: 0 0 6px;
  letter-spacing: 2px;
}
.ts-login-subtitle {
  font-size: 13px;
  color: #64748b;
  letter-spacing: 2px;
  margin: 0;
}
.ts-login-form :deep(.el-input__wrapper) {
  height: 44px;
  background: rgba(15, 23, 42, 0.8) !important;
  border-color: rgba(148, 163, 184, 0.15) !important;
}
.ts-login-form :deep(.el-input__inner) {
  color: #f1f5f9 !important;
}
.ts-login-form :deep(.el-input__inner::placeholder) {
  color: #64748b !important;
}
.ts-login-btn {
  width: 100%;
  height: 44px !important;
  font-size: 15px !important;
  letter-spacing: 4px;
}
</style>
