<template>
  <div style="display: flex; align-items: center; justify-content: center; height: 100vh; background: #1a1a2e">
    <el-card style="width: 400px">
      <template #header>
        <h2 style="text-align: center; margin: 0">韬盛ERP 登录</h2>
      </template>
      <el-form :model="form" @submit.prevent="handleLogin">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">登录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

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
