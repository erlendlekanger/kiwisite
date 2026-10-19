const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1179,height:2556}});
await p.goto('file://'+process.cwd()+'/screen.html');await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
await p.screenshot({path:'screen.png'});await b.close();console.log('shot');})();
