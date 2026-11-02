const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const html=fs.readFileSync("static/index.html","utf8");
const start=html.indexOf("let sentimentRequestVersion =");
const end=html.indexOf("// SCREENER",start);
assert.ok(start>0&&end>start);
function harness(){
 const nodes=new Map(),calls=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{innerText:"",innerHTML:"",style:{},disabled:false});return nodes.get(id);};
 const ctx={document:{getElementById:node},URL,console,
  escapeRoutingText:value=>String(value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])),
  apiCall:async()=>{calls.push(1);return ctx.response();}};
 vm.createContext(ctx);vm.runInContext(html.slice(start,end),ctx);
 return {ctx,node,calls};
}
const fixture=()=>({score:56,label:"neutral",reasoning:"formula",methodology:{description:"project mapping"},
 components:{vix:{status:"available",raw_value:19.42,score:52.9,as_of:"2026-10-30",source:"Cboe",source_url:"https://example.invalid/vix",fetched_at:"fixture"},
 news:{status:"available",score:70,eligible_count:1,scored_count:1}},contributions:{vix:42.32,news:14},
 news_analysis:[{title:"<img src=x onerror=evil()>",summary:"<script>evil()</script>",source:"fixture",link:"javascript:evil()",published_at:"2026-10-30",sentiment:"positive"}]});
(async()=>{
 const h=harness();let resolve;h.ctx.response=()=>new Promise(r=>resolve=r);
 h.node("sentiment-score").innerText="99";h.node("sentiment-components").innerHTML="old";
 const pending=h.ctx.fetchSentiment();
 assert.equal(h.node("btn-sentiment").disabled,true);assert.equal(h.node("sentiment-components").innerHTML,"");
 assert.notEqual(h.node("sentiment-score").innerText,"99");
 resolve(fixture());await pending;
 assert.equal(h.node("sentiment-score").innerText,56);assert.equal(h.node("btn-sentiment").disabled,false);
 assert.match(h.node("sentiment-components").innerHTML,/VIX 80%/);assert.match(h.node("sentiment-components").innerHTML,/20%/);
 assert.match(h.node("sentiment-components").innerHTML,/19.42/);assert.match(h.node("sentiment-components").innerHTML,/42.32/);
 assert.match(h.node("sentiment-news-grid").innerHTML,/&lt;img/);assert.doesNotMatch(h.node("sentiment-news-grid").innerHTML,/<script|href="javascript:/);
 h.ctx.response=async()=>({...fixture(),score:0});await h.ctx.fetchSentiment();
 assert.equal(h.node("sentiment-score").innerText,0);
 h.ctx.response=async()=>({...fixture(),score:null});await h.ctx.fetchSentiment();
 assert.equal(h.node("sentiment-score").innerText,"\u2014");
 h.ctx.response=async()=>{throw new Error("offline");};await h.ctx.fetchSentiment();
 assert.equal(h.node("sentiment-components").innerHTML,"");assert.equal(h.node("sentiment-news-grid").innerHTML,"");
 assert.equal(h.node("btn-sentiment").disabled,false);
 const waits=[];h.ctx.response=()=>new Promise(r=>waits.push(r));
 const first=h.ctx.fetchSentiment(),second=h.ctx.fetchSentiment();
 waits[1]({...fixture(),score:22});await second;waits[0]({...fixture(),score:88});await first;
 assert.equal(h.node("sentiment-score").innerText,22);
 console.log("actual radar UI loading/null/failure/escape/source/weights/race checks passed");
})().catch(error=>{console.error(error);process.exitCode=1;});
