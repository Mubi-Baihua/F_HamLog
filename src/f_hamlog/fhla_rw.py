'''
用于处理fhla文件格式的模块，使原有的project.py能够支持。
fhla支持自定义日志项，以及其他新功能
'''
from f_hamlog import fhl_rw

class fhla_project():
    def __init__(self, fhla_dict):
        '''fhla_file:fhla的json，使用dict'''
        self.input_fhla_project(fhla_dict)

    def get_other_item(self):
        if not('other_item' in self.xml.keys()):
            raise ValueError(f'未找到合法的keys,self.xml.keys:{self.xml.keys()}')
        return self.xml['other_item']

    def write_other_item(self,other_item):
        self.xml['other_item'] = other_item

    def get_xml(self):
        return self.xml

    def write_xml(self,xml):
        self['xml'] = xml

    def input_fhla_project(self,fhla_dict):
        if  not('xml' in fhla_dict.keys() and 'project' in fhla_dict.keys()):
            raise ValueError(f'未找到合法的keys,fhla_dict.keys:{fhla_dict.keys()}')
        self.xml = fhla_dict['xml']
        self.project = fhla_dict['project']

    def output_fhla_project(self):
        return {'xml':self.xml,'project':self.project}

    def get_fhl(self):
        return self.project

    def write_fhl(self,fhl):
        self.project = fhl

if __name__ == "__main__":
    f = fhla_project({'123':123,"234":234})