import torch
from torch import nn
def gn(c):
    g=min(8,c)
    while c%g:g-=1
    return nn.GroupNorm(g,c)
class Block(nn.Module):
    def __init__(self,a,b,stride=1):
        super().__init__();self.c1=nn.Conv2d(a,b,3,stride,padding=1,bias=False);self.n1=gn(b)
        self.c2=nn.Conv2d(b,b,3,padding=1,bias=False);self.n2=gn(b)
        self.skip=nn.Identity() if a==b and stride==1 else nn.Sequential(nn.Conv2d(a,b,1,stride,bias=False),gn(b))
        self.act=nn.SiLU()
    def forward(self,x):return self.act(self.n2(self.c2(self.act(self.n1(self.c1(x)))))+self.skip(x))
class ResNet18GN(nn.Module):
    def __init__(self,classes=10,width=32):
        super().__init__();self.stem=nn.Sequential(nn.Conv2d(3,width,3,padding=1,bias=False),gn(width),nn.SiLU())
        blocks=[];a=width
        for i,b in enumerate([width,2*width,4*width,8*width]):
            blocks.extend([Block(a,b,1 if i==0 else 2),Block(b,b)]);a=b
        self.blocks=nn.Sequential(*blocks);self.head=nn.Linear(a,classes)
    def forward(self,x):return self.head(self.blocks(self.stem(x)).mean((2,3)))
