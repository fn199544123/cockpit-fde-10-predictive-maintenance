#!/usr/bin/env python3
"""在 GPU 宿主机执行：python3 smoke-test.py [--url URL]。需 playwright + Chromium。"""
import argparse,json,hashlib,threading,http.server,functools
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--url');args=parser.parse_args()
if not args.url:
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    args.url=f'http://127.0.0.1:{server.server_port}/index.html'
checks=[]
def check(name,condition):
    assert condition,name
    checks.append({'name':name,'passed':True})
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1100},accept_downloads=True)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    response=page.goto(args.url)
    check('HTTP 200',response.status==200)
    data=lambda:page.evaluate('JSON.parse(localStorage.getItem("development-10-maintenance-v1"))')
    def fill(**kw):
        for k,v in kw.items():page.locator(f'[name="{k}"]').fill(str(v))
    def save():page.locator('#form button[type=submit]').click()
    page.get_by_role('button',name='重置演示数据').click() if False else None
    page.evaluate('localStorage.removeItem("development-10-maintenance-v1")');page.reload()
    check('初始到期保养自动生成一张工单',len(data()['orders'])==1)
    page.get_by_role('button',name='检查到期保养').click();page.reload()
    check('重复检查和刷新不重复派工',len(data()['orders'])==1)
    page.get_by_role('button',name='＋ 新增设备').click()
    fill(id='SIM-E099',name='测试循环泵',hours=10,next=20,interval=100,tempMax=80,vibMax=5);save()
    page.locator('#search').fill('SIM-E099');check('新增和筛选设备',page.locator('#devices tr').count()==1 and len(data()['devices'])==4)
    page.locator('[data-edit="SIM-E099"]').click();fill(name='测试循环泵改');save()
    check('设备编辑保存',data()['devices'][-1]['name']=='测试循环泵改')
    page.locator('[data-read="SIM-E099"]').click();fill(hours=20,temp=90,vib=6);save()
    check('读数、运行时长、阈值预警、自动派工联动',data()['devices'][-1]['hours']==20 and len(data()['orders'])==2 and '阈值预警' in page.locator('#devices').inner_text())
    page.locator('[data-read="SIM-E099"]').click();fill(hours=19,temp=20,vib=1);save()
    check('拒绝累计时长回退','不能回退' in page.locator('#formError').inner_text() and data()['devices'][-1]['hours']==20)
    fill(hours=21,temp=-1,vib=1);save();check('拒绝负读数',page.locator('#modal').evaluate('(e)=>e.open') and len(data()['devices'][-1]['readings'])==1)
    page.get_by_role('button',name='取消',exact=True).click()
    for hours,temp,vib in [(21,91,6.2),(22,92,6.5)]:
        page.locator('[data-read="SIM-E099"]').click();fill(hours=hours,temp=temp,vib=vib);save()
    page.locator('#trendSelect').select_option('SIM-E099')
    check('趋势图展示三次采集',page.locator('#trend circle').count()==6)
    page.get_by_role('button',name='检查到期保养').click();check('持续到期仍不重复派工',len(data()['orders'])==2)
    page.locator('[data-complete="SIM-W0002"]').click();page.locator('[name=part]').select_option('SIM-P001');fill(qty=4);save()
    check('超库存完成保养被拒绝且工单和库存不变','超过库存' in page.locator('#formError').inner_text() and data()['parts'][0]['stock']==3 and data()['orders'][-1]['status']=='待处理')
    fill(qty=2);save()
    check('完成保养扣库存并更新下次保养',data()['parts'][0]['stock']==1 and data()['devices'][-1]['next']==122 and data()['orders'][-1]['status']=='已完成' and data()['logs'][-1]['delta']==-2)
    page.locator('[data-stock="SIM-P001"]').click();fill(qty=-1);save();check('拒绝负库存变动',data()['parts'][0]['stock']==1 and page.locator('#modal').evaluate('(e)=>e.open'))
    fill(qty=5);save();check('入库解除低库存提醒',data()['parts'][0]['stock']==6 and '低库存' not in page.locator('#parts tr').first.inner_text())
    page.locator('[data-stock="SIM-P001"]').click();page.locator('[name=kind]').select_option('out');fill(qty=7);save();check('独立领用拒绝超库存',data()['parts'][0]['stock']==6 and '超过库存' in page.locator('#formError').inner_text());fill(qty=4);save()
    check('领用与低库存提醒联动',data()['parts'][0]['stock']==2 and '低库存' in page.locator('#parts tr').first.inner_text())
    page.get_by_role('button',name='＋ 新增备件').click();fill(id='SIM-P099',name='测试备件',stock=5,min=2);save()
    page.locator('[data-part="SIM-P099"]').click();fill(name='测试备件改',min=6);save();check('新增编辑备件',data()['parts'][-1]['name']=='测试备件改' and data()['parts'][-1]['min']==6)
    with page.expect_download() as download:page.get_by_role('button',name='导出当前设备 CSV').click()
    path=download.value.path();csv=Path(path).read_text(encoding='utf-8-sig')
    check('CSV 与筛选一致',len(csv.splitlines())==2 and 'SIM-E099' in csv)
    page.reload();check('刷新持久化读数工单库存',data()['parts'][0]['stock']==2 and data()['devices'][-1]['next']==122 and len(data()['devices'][-1]['readings'])==3)
    page.locator('#workshop').select_option('一车间');page.locator('#status').select_option('alarm');check('组合筛选',page.locator('#devices tr').count()==2)
    page.once('dialog',lambda d:d.dismiss());page.get_by_role('button',name='重置演示数据').click();check('取消重置保留数据',len(data()['devices'])==4)
    page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='重置演示数据').click();check('确认重置恢复初始数据',len(data()['devices'])==3 and data()['parts'][0]['stock']==3 and len(data()['orders'])==1)
    page.screenshot(path=str(ROOT/'acceptance-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(ROOT/'acceptance-mobile.png'),full_page=True)
    check('390px 手机无整页横向溢出',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    check('浏览器无脚本错误',not errors)
    browser.close()
result={'passed':True,'checks':checks,'html_sha256':hashlib.sha256((ROOT/'index.html').read_bytes()).hexdigest(),'runtime':'GPU 宿主机 fangnangpu / Chromium / Playwright','url':args.url,'screenshots':['acceptance-desktop.png','acceptance-mobile.png']}
(ROOT/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
