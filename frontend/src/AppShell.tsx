import { BarChartOutlined, SettingOutlined, ToolOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import { Link, Outlet, useLocation } from 'react-router-dom'

const { Header, Content, Sider } = Layout

export default function AppShell() {
  const location = useLocation()

  return (
    <Layout style={{ minHeight: '100vh' }} className="app-layout">
      <Sider theme="light" width={236} className="app-sider">
        <div className="app-brand">
          <div className="app-brand-dot" />
          <div>
            <div className="app-brand-title">ToolFlow</div>
            <div className="app-brand-subtitle">Control Plane</div>
          </div>
        </div>
        <Menu
          mode="inline"
          className="app-menu"
          selectedKeys={[location.pathname]}
          items={[
            { key: '/tools', icon: <ToolOutlined />, label: <Link to="/tools">Tools</Link> },
            {
              key: '/executions',
              icon: <UnorderedListOutlined />,
              label: <Link to="/executions">Executions</Link>,
            },
            {
              key: '/metrics',
              icon: <BarChartOutlined />,
              label: <Link to="/metrics">Executors</Link>,
            },
            {
              key: '/settings',
              icon: <SettingOutlined />,
              label: <Link to="/settings">Settings</Link>,
            },
          ]}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <Typography.Title level={4} style={{ margin: 0 }}>
            ToolFlow
          </Typography.Title>
        </Header>
        <Content style={{ padding: 20 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
